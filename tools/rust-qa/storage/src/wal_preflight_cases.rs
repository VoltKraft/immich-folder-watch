use super::{Result, UnsupportedSchema, digest_file, ensure, preflight, sidecar};
use rusqlite::{Connection, config::DbConfig};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

fn fingerprint(directory: &Path) -> Result<BTreeMap<String, String>> {
    let mut files = BTreeMap::new();
    for entry in fs::read_dir(directory)? {
        let path = entry?.path();
        let name = path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("expected fixture name")?;
        files.insert(name.to_owned(), digest_file(&path)?);
    }
    Ok(files)
}

pub(super) fn run(output: &Path) -> Result<Vec<Value>> {
    let mut cases = Vec::new();
    for (name, base, latest, keep_shm) in [
        ("newer-with-index", 1_i64, 99_i64, true),
        ("newer-without-index", 1, 99, false),
        ("supported-without-index", 0, 1, false),
    ] {
        let directory = output.join(name);
        fs::create_dir(&directory)?;
        let path = directory.join("state.db");
        let db = Connection::open(&path)?;
        db.execute_batch("PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0; CREATE TABLE sample(value INTEGER);")?;
        db.pragma_update(None, "user_version", base)?;
        db.execute_batch("PRAGMA wal_checkpoint(TRUNCATE); BEGIN;")?;
        db.pragma_update(None, "user_version", latest)?;
        db.execute("INSERT INTO sample VALUES(?1)", [latest])?;
        db.execute_batch("COMMIT;")?;
        db.set_db_config(DbConfig::SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, true)?;
        db.close().map_err(|(_, error)| error)?;
        if !keep_shm {
            fs::remove_file(sidecar(&path, "-shm"))?;
        }
        let main = fs::read(&path)?;
        let physical = i32::from_be_bytes(main[60..64].try_into()?);
        ensure(
            i64::from(physical) == base,
            "expected the prior version in the main database",
        )?;
        let wal_bytes = fs::metadata(sidecar(&path, "-wal"))?.len();
        ensure(
            wal_bytes > 32,
            "expected committed frames in the original WAL",
        )?;
        let before = fingerprint(&directory)?;
        let scratch = output.join("preflight");
        let opened = preflight::open_existing(&path, &scratch);
        let mut record = json!({"Case": name, "MainVersion": physical, "CommittedVersion": latest,
                                "WalBytes": wal_bytes, "SourceBefore": before});
        if latest == 99 {
            let error = opened.err().ok_or("future profile was opened")?;
            ensure(
                matches!(
                    error.downcast_ref::<UnsupportedSchema>(),
                    Some(UnsupportedSchema(99))
                ),
                "expected the committed future schema version",
            )?;
            let after = fingerprint(&directory)?;
            ensure(
                before == after && before.contains_key("state.db-shm") == keep_shm,
                "future database or its sidecars changed",
            )?;
            record["RejectedVersion"] = json!(latest);
            record["SourceAfter"] = json!(after);
        } else {
            let mut ready = opened?;
            let row: i64 = ready.query_one("SELECT value FROM sample", [], |r| r.get(0))?;
            ensure(
                row == latest,
                "first supported connection lost the committed WAL row",
            )?;
            record["OpenedValue"] = json!(row);
            let write = ready.transaction()?;
            ensure(
                write.execute("UPDATE sample SET value=2 WHERE value=1", [])? == 1,
                "unable to write the supported profile",
            )?;
            write.rollback()?;
            record["WriteRolledBack"] = json!(true);
        }
        ensure(
            !scratch.try_exists()?,
            "private inspection directory survived handoff",
        )?;
        cases.push(record);
    }
    Ok(cases)
}

pub(super) fn persistent_journal(output: &Path) -> Result<Value> {
    let directory = output.join("newer-with-finalized-journal");
    fs::create_dir(&directory)?;
    let path = directory.join("state.db");
    let writer = Connection::open(&path)?;
    writer.execute_batch(
        "PRAGMA journal_mode=PERSIST; CREATE TABLE sample(value INTEGER); PRAGMA user_version=99;",
    )?;
    writer.close().map_err(|(_, error)| error)?;
    let before = fingerprint(&directory)?;
    ensure(
        before.contains_key("state.db-journal"),
        "SQLite did not retain its finalized journal",
    )?;
    let scratch = output.join("preflight");
    let error = preflight::open_existing(&path, &scratch)
        .err()
        .ok_or("future schema with a persistent journal was opened")?;
    ensure(
        matches!(
            error.downcast_ref::<UnsupportedSchema>(),
            Some(UnsupportedSchema(99))
        ),
        "expected a version refusal for the finalized journal",
    )?;
    let after = fingerprint(&directory)?;
    ensure(
        before == after && !scratch.try_exists()?,
        "persistent journal preflight changed inputs",
    )?;
    Ok(json!({"RejectedVersion": 99, "SourceBefore": before, "SourceAfter": after}))
}

pub(super) fn read_only_database(output: &Path) -> Result<Value> {
    let directory = output.join("supported-read-only");
    fs::create_dir(&directory)?;
    let path = directory.join("state.db");
    let writer = Connection::open(&path)?;
    writer.execute_batch(
        "PRAGMA journal_mode=WAL; PRAGMA user_version=1; CREATE TABLE sample(value INTEGER);",
    )?;
    writer.close().map_err(|(_, error)| error)?;
    let before = fingerprint(&directory)?;
    let original = fs::metadata(&path)?.permissions();
    let mut protected = original.clone();
    protected.set_readonly(true);
    fs::set_permissions(&path, protected)?;
    let observed = (|| -> Result<Value> {
        match fs::OpenOptions::new().write(true).open(&path) {
            Ok(_) => {
                return Ok(
                    json!({"Observed": false, "Reason": "the host user can still write this file"}),
                );
            }
            Err(error) if error.kind() == std::io::ErrorKind::PermissionDenied => {}
            Err(error) => return Err(error.into()),
        }
        let scratch = output.join("preflight");
        let error = preflight::open_existing(&path, &scratch)
            .err()
            .ok_or("SQLite read-only fallback reached the writer")?;
        let permission = error
            .downcast_ref::<std::io::Error>()
            .is_some_and(|cause| cause.kind() == std::io::ErrorKind::PermissionDenied);
        let sqlite = error
            .downcast_ref::<rusqlite::Error>()
            .and_then(|cause| cause.sqlite_error_code());
        ensure(
            permission
                || matches!(
                    sqlite,
                    Some(
                        rusqlite::ErrorCode::ReadOnly
                            | rusqlite::ErrorCode::CannotOpen
                            | rusqlite::ErrorCode::PermissionDenied
                    )
                ),
            "unexpected read-only preflight failure",
        )?;
        let after = fingerprint(&directory)?;
        ensure(
            before == after && !scratch.try_exists()?,
            "read-only refusal changed the profile",
        )?;
        Ok(
            json!({"Observed": true, "Error": error.to_string(), "SourceBefore": before, "SourceAfter": after}),
        )
    })();
    fs::set_permissions(&path, original)?;
    observed
}
