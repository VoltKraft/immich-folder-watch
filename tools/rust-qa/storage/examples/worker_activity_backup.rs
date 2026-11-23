//! Return a finalized SQLite backup to the running synthetic worker assessment.
#![forbid(unsafe_code)]

use ifw_legacy::timestamp::UtcTicks;
use ifw_sqlite_assessment::{Result, digest, field, limited, verify_backup};
use rusqlite::backup::Backup;
use rusqlite::types::Value as SqlValue;
use rusqlite::{Connection, OpenFlags, OptionalExtension, params};
use serde_json::{Value, json};
use std::ffi::OsStr;
use std::fs::{self, File, OpenOptions};
use std::io::{ErrorKind, Read};
use std::path::Path;
use std::time::Duration;

#[cfg(windows)]
const GOLDEN: &str =
    include_str!("../../../../rust/tests/fixtures/legacy/windows/sqlite/sensitive.sql");
#[cfg(not(windows))]
const GOLDEN: &str =
    include_str!("../../../../rust/tests/fixtures/legacy/linux/sqlite/sensitive.sql");
const RETURNED: &str = "returned.db";
const MAX_DB_BYTES: u64 = 16 * 1024 * 1024;
type Catalog = Vec<(String, String, String, Option<String>)>;

fn lower_hex(value: &str, size: usize) -> bool {
    value.len() == size
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

fn select_exchange(path: &Path) -> Result<()> {
    let checkout = fs::canonicalize(".")?;
    if checkout != fs::canonicalize(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../.."))? {
        return Err("run the activity backup from its source checkout".into());
    }
    let artifacts = checkout.join("artifacts/rust");
    let resolved = fs::canonicalize(path)?;
    if fs::canonicalize(&artifacts)? != artifacts
        || !resolved.starts_with(&artifacts)
        || path.file_name() != Some(OsStr::new("exchange"))
        || resolved.file_name() != path.file_name()
        || !fs::symlink_metadata(path)?.is_dir()
    {
        return Err("expected the prepared exchange directory below artifacts/rust".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if fs::metadata(&resolved)?.permissions().mode() & 0o077 != 0 {
            return Err("the exchange directory must be owner-only".into());
        }
    }
    // All SQLite URI filenames below are literals relative to the private exchange.
    std::env::set_current_dir(resolved)?;
    Ok(())
}

fn read_request() -> Result<Value> {
    let path = Path::new("request.json");
    if !fs::symlink_metadata(path)?.is_file() {
        return Err("expected a regular worker request".into());
    }
    let request: Value = serde_json::from_slice(&limited(File::open(path)?, 4096)?)?;
    if request["format"] != "ifw-worker-backup-request-v1"
        || !lower_hex(field(&request, "token")?, 32)
        || !lower_hex(field(&request, "beforeSha256")?, 64)
        || !lower_hex(field(&request, "afterSha256")?, 64)
    {
        return Err("invalid worker backup request".into());
    }
    Ok(request)
}

fn immutable(name: &str) -> Result<Connection> {
    let mut header = [0; 20];
    File::open(name)?.read_exact(&mut header)?;
    if &header[..16] != b"SQLite format 3\0" || header[18..20] != [1, 1] {
        return Err("expected a finalized rollback-journal database".into());
    }
    let db = Connection::open_with_flags(
        format!("file:{name}?mode=ro&immutable=1"),
        OpenFlags::SQLITE_OPEN_READ_ONLY
            | OpenFlags::SQLITE_OPEN_URI
            | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )?;
    db.execute_batch("PRAGMA trusted_schema=OFF; PRAGMA query_only=ON;")?;
    Ok(db)
}

fn catalog(db: &Connection) -> rusqlite::Result<Catalog> {
    db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name")?
        .query_map([], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?))
        })?
        .collect()
}

fn canonical_catalog(mut rows: Catalog) -> Catalog {
    // The native C# compiler preserves host line endings in multiline SQL strings.
    for (_, _, _, sql) in &mut rows {
        if let Some(sql) = sql {
            *sql = sql.replace("\r\n", "\n");
        }
    }
    rows
}

fn single_row(db: &Connection, sql: &str) -> rusqlite::Result<Vec<SqlValue>> {
    let mut stmt = db.prepare(sql)?;
    let columns = stmt.column_count();
    stmt.query_one([], |row| (0..columns).map(|i| row.get(i)).collect())
}

#[derive(PartialEq)]
struct Download {
    schema: Catalog,
    entries: Vec<SqlValue>,
    account_status: Vec<SqlValue>,
    counts: [i64; 4],
}

fn read_download(db: &Connection, golden: &Catalog) -> Result<Option<Download>> {
    let schema = catalog(db)?;
    if db.query_one::<i64, _, _>("PRAGMA user_version", [], |r| r.get(0))? != 1
        || db.query_one::<String, _, _>("PRAGMA integrity_check", [], |r| r.get(0))? != "ok"
        || &canonical_catalog(schema.clone()) != golden
    {
        return Err(
            "the database differs from the reviewed v1 schema or fails integrity checking".into(),
        );
    }
    let counts = db.query_one(
        "SELECT (SELECT count(*) FROM owned_albums), (SELECT count(*) FROM sync_account_status),
                (SELECT count(*) FROM sync_entries), (SELECT count(*) FROM sync_timestamp_repairs)",
        [],
        |r| Ok([r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?]),
    )?;
    if counts == [0; 4] {
        return Ok(None);
    }
    if counts != [0, 1, 1, 0] {
        return Err("unexpected worker activity counts".into());
    }
    let key = if cfg!(windows) {
        "PHOTO.JPG"
    } else {
        "photo.jpg"
    };
    let modified = if cfg!(windows) {
        "2004-02-06T06:08:10.0000000+00:00"
    } else {
        "2004-02-04T06:08:10.0000000+00:00"
    };
    let (source, synchronized, history): (String, String, String) = db.query_one(
        "SELECT e.source_path, e.last_synchronized_at_utc, a.last_successful_sync_utc
         FROM sync_entries AS e JOIN sync_account_status AS a USING(account_scope)
         WHERE e.account_scope=?1 AND e.relative_path='photo.jpg' AND e.relative_path_key=?2
           AND e.asset_id='remote' AND e.album_name='Camera' AND e.file_size=6 AND e.last_write_time_utc=?3
           AND e.direction=1 AND e.status=0 AND e.tombstone_expires_at_utc IS NULL",
        params![digest(b"https://immich.example/api\ntest-key"), key, modified],
        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
    ).optional()?.ok_or("mapping or account history differs from the synthetic download")?;
    let source = Path::new(&source);
    let temp_id = source
        .parent()
        .and_then(Path::file_name)
        .and_then(OsStr::to_str)
        .and_then(|name| name.strip_prefix("immich-folder-watch-worker-tests-"));
    if !source.is_absolute()
        || source.file_name() != Some(OsStr::new("watch"))
        || !temp_id.is_some_and(|id| lower_hex(id, 32))
        || UtcTicks::parse_sql(&history)? < UtcTicks::parse_sql(&synchronized)?
    {
        return Err("unexpected synthetic source or last successful sync".into());
    }
    Ok(Some(Download {
        schema,
        counts,
        entries: single_row(db, "SELECT * FROM sync_entries")?,
        account_status: single_row(db, "SELECT * FROM sync_account_status")?,
    }))
}

fn require_fresh_destination() -> Result<()> {
    for name in [
        RETURNED,
        "returned.db-journal",
        "returned.db-wal",
        "returned.db-shm",
    ] {
        match fs::symlink_metadata(name) {
            Ok(_) => return Err("destination or its SQLite companions already exist".into()),
            Err(e) if e.kind() == ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}

fn reserve_destination() -> Result<()> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options.open(RETURNED)?;
    Ok(())
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let [directory, phase, hash] = args.as_slice() else {
        return Err(
            "usage: worker_activity_backup <exchange> <before|after> <snapshot-sha256>".into(),
        );
    };
    let (name, hash_field) = match phase.to_str() {
        Some("before") => ("before.db", "beforeSha256"),
        Some("after") => ("after.db", "afterSha256"),
        _ => return Err("expected before or after".into()),
    };
    select_exchange(Path::new(directory))?;
    let request = read_request()?;
    let expected = field(&request, hash_field)?;
    if hash.to_str() != Some(expected) {
        return Err("requested donor digest differs from the worker observation".into());
    }
    verify_backup(Path::new(name), expected)?;
    let donor = immutable(name)?;
    let sqlite_source: String = donor.query_one("SELECT sqlite_source_id()", [], |r| r.get(0))?;
    let options: Vec<String> = donor
        .prepare("PRAGMA compile_options")?
        .query_map([], |r| r.get(0))?
        .collect::<rusqlite::Result<_>>()?;
    let reviewed: Value = serde_json::from_str(include_str!("../inputs.json"))?;
    if reviewed["sqlite"]["version"] != rusqlite::version()
        || reviewed["sqlite"]["source_id"] != sqlite_source
        || !options.iter().any(|s| s == "OMIT_LOAD_EXTENSION")
        || options.iter().any(|s| s == "ENABLE_LOAD_EXTENSION")
        || donor.query_one::<i64, _, _>(
            "SELECT count(*) FROM pragma_function_list WHERE name='load_extension'",
            [],
            |r| r.get(0),
        )? != 0
    {
        return Err("unexpected SQLite build or extension-loading capability".into());
    }
    let golden = Connection::open_in_memory()?;
    golden.execute_batch(GOLDEN)?;
    let golden = canonical_catalog(catalog(&golden)?);
    let observed = read_download(&donor, &golden)?;
    require_fresh_destination()?;
    let Some(original) = observed else {
        donor.close().map_err(|(_, error)| error)?;
        verify_backup(Path::new(name), expected)?;
        eprintln!(
            "IFW_WORKER_STALE={}",
            json!({
                "format":"ifw-worker-backup-stale-v1", "token":request["token"], "sourceSha256":expected
            })
        );
        return Err("no completed worker download".into());
    };
    reserve_destination()?;
    let mut destination = Connection::open_with_flags(
        RETURNED,
        OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )?;
    destination.execute_batch("PRAGMA trusted_schema=OFF;")?;
    Backup::new(&donor, &mut destination)?.run_to_completion(16, Duration::from_millis(1), None)?;
    if destination.query_one::<String, _, _>("PRAGMA journal_mode=DELETE", [], |r| r.get(0))?
        != "delete"
    {
        return Err("could not finalize returned SQLite backup".into());
    }
    destination.close().map_err(|(_, error)| error)?;
    donor.close().map_err(|(_, error)| error)?;
    let restored_hash = digest(&limited(File::open(RETURNED)?, MAX_DB_BYTES)?);
    verify_backup(Path::new(RETURNED), &restored_hash)?;
    if read_download(&immutable(RETURNED)?, &golden)?.as_ref() != Some(&original) {
        return Err("reopened Rust backup differs from the finalized worker state".into());
    }
    verify_backup(Path::new(RETURNED), &restored_hash)?;
    verify_backup(Path::new(name), expected)?;
    let [owned, status, entries, repairs] = original.counts;
    serde_json::to_writer(
        std::io::stdout().lock(),
        &json!({
            "format":"ifw-rust-worker-activity-backup-v1", "token":request["token"],
            "sourceSha256":expected, "restoredSha256":restored_hash, "sqliteSourceId":sqlite_source,
            "sqliteVersion":rusqlite::version(), "compileOptions":options,
            "os":std::env::consts::OS, "arch":std::env::consts::ARCH,
            "tableRows":{"owned_albums":owned,"sync_account_status":status,"sync_entries":entries,"sync_timestamp_repairs":repairs}
        }),
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_a_valid_empty_snapshot_qualifies_as_stale() -> Result<()> {
        let db = Connection::open_in_memory()?;
        db.execute_batch(GOLDEN)?;
        let golden = canonical_catalog(catalog(&db)?);
        db.execute_batch("DELETE FROM owned_albums; DELETE FROM sync_entries; DELETE FROM sync_timestamp_repairs;")?;
        assert!(read_download(&db, &golden).is_err()); // Inconsistent account history survives.
        db.execute_batch("DELETE FROM sync_account_status;")?;
        assert!(read_download(&db, &golden)?.is_none());
        db.execute_batch("PRAGMA user_version=2;")?;
        assert!(read_download(&db, &golden).is_err());
        Ok(())
    }
}
