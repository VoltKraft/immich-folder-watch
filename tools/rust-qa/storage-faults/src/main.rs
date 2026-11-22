//! Bounded native fault experiment. This is not a production storage adapter.
#![forbid(unsafe_code)]

use rusqlite::{Connection, OpenFlags, backup::Backup, params};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::error::Error;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::Duration;

include!(concat!(env!("OUT_DIR"), "/reviewed-module.rs"));

type Result<T> = std::result::Result<T, Box<dyn Error>>;
const CONFIRMED_TIME: &str = "2026-01-02T03:04:05.1234567+00:00";
const PENDING_TIME: &str = "2026-02-03T04:05:06.7654321+00:00";
const PAYLOAD_BYTES: usize = 2 * 1024 * 1024;
const SOURCE_ID: &str =
    "2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76";

fn check(value: bool, message: &str) -> Result<()> {
    if !value {
        return Err(message.into());
    }
    Ok(())
}

fn digest(path: &Path) -> Result<String> {
    Ok(Sha256::digest(std::fs::read(path)?)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn write_json(path: &Path, value: &Value) -> Result<()> {
    std::fs::write(path, serde_json::to_vec_pretty(value)?)?;
    Ok(())
}

fn load_json(path: &Path) -> Result<Value> {
    Ok(serde_json::from_slice(&std::fs::read(path)?)?)
}

fn emit(value: &Value) -> Result<()> {
    println!("{}", serde_json::to_string(value)?);
    io::stdout().flush()?;
    Ok(())
}

fn integrity(database: &Connection) -> Result<()> {
    let rows: Vec<String> = database
        .prepare("PRAGMA integrity_check")?
        .query_map([], |row| row.get(0))?
        .collect::<rusqlite::Result<_>>()?;
    check(
        rows == ["ok"],
        "SQLite integrity_check did not return exactly ok",
    )
}

fn authenticate_snapshot(path: &Path, expected: &str) -> Result<String> {
    check(
        expected.len() == 64
            && expected
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)),
        "invalid producer SHA-256",
    )?;
    let actual = digest(path)?;
    check(
        actual == expected,
        "SNAPSHOT_SHA256_MISMATCH: retained backup differs from producer",
    )?;
    Ok(actual)
}

fn snapshot_copy(source: &Path, destination: &Path, expected: &str) -> Result<()> {
    authenticate_snapshot(source, expected)?;
    let wal = source.with_file_name(format!(
        "{}-wal",
        source
            .file_name()
            .ok_or("snapshot filename")?
            .to_string_lossy()
    ));
    check(
        !wal.exists() || std::fs::metadata(wal)?.len() == 0,
        "snapshot has live WAL",
    )?;
    check(!destination.exists(), "snapshot copy already exists")?;
    std::fs::copy(source, destination)?;
    authenticate_snapshot(destination, expected)?;
    authenticate_snapshot(source, expected)?;
    Ok(())
}

fn backup(source: &Connection, destination: &Path) -> Result<String> {
    check(!destination.exists(), "backup target already exists")?;
    let expected = reviewed::fault_snapshot(source)?;
    let mut target = Connection::open(destination)?;
    Backup::new(source, &mut target)?.run_to_completion(2, Duration::from_millis(1), None)?;
    target.close().map_err(|(_, error)| error)?;
    // Anchor the closed API result before any verifier opens the destination.
    // The supervisor retains this producer event independently of later readers.
    let sha256 = digest(destination)?;
    emit(
        &json!({"phase":"backup-completed", "file":destination.file_name().ok_or("backup filename")?.to_string_lossy(),
        "sha256":sha256, "bytes":std::fs::metadata(destination)?.len()}),
    )?;
    let target = Connection::open_with_flags(destination, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    integrity(&target)?;
    check(
        expected == reviewed::fault_snapshot(&target)?,
        "backup API changed full schema/table snapshot",
    )?;
    target.close().map_err(|(_, error)| error)?;
    authenticate_snapshot(destination, &sha256)
}

fn expected_state(mut expected: Value, pending: bool) -> Result<Value> {
    let (asset, album, time) = if pending {
        ("asset-unacknowledged", "album-unacknowledged", PENDING_TIME)
    } else {
        ("asset-confirmed", "album-confirmed", CONFIRMED_TIME)
    };
    for entry in expected["Entries"]
        .as_array_mut()
        .ok_or("missing entries")?
    {
        if entry["RelativePath"] == "download.bin" {
            entry["AssetId"] = json!(asset);
            entry["LastSynchronizedAtUtc"] = json!(time);
        }
    }
    expected["OwnedAlbumId"] = json!(album);
    expected["LastSuccessfulSyncUtc"] = json!(time);
    expected["Repairs"][0]["CreationTimeUtc"] = json!(time);
    Ok(expected)
}

fn update_four_tables(database: &Connection, expected: &Value, payload: bool) -> Result<()> {
    let account = expected["Account"].as_str().ok_or("missing account")?;
    let entry = expected["Entries"]
        .as_array()
        .ok_or("missing entries")?
        .iter()
        .find(|entry| entry["RelativePath"] == "download.bin")
        .ok_or("missing download")?;
    let time = expected["LastSuccessfulSyncUtc"]
        .as_str()
        .ok_or("missing time")?;
    check(database.execute(
        "UPDATE sync_entries SET asset_id=?1,last_synchronized_at_utc=?2 WHERE account_scope=?3 AND relative_path=?4",
        params![entry["AssetId"].as_str(), time, account, "download.bin"],
    )? == 1, "entry scope changed")?;
    check(
        database.execute(
            "UPDATE owned_albums SET album_id=?1 WHERE account_scope=?2",
            params![expected["OwnedAlbumId"].as_str(), account],
        )? == 1,
        "album scope changed",
    )?;
    check(
        database.execute(
            "UPDATE sync_account_status SET last_successful_sync_utc=?1 WHERE account_scope=?2",
            params![time, account],
        )? == 1,
        "history scope changed",
    )?;
    let mut repair = expected["Repairs"][0].clone();
    if payload {
        repair["FaultExperimentPayload"] = json!("x".repeat(PAYLOAD_BYTES));
    }
    check(
        database.execute(
            "UPDATE sync_timestamp_repairs SET repair_json=?1 WHERE account_scope=?2",
            params![serde_json::to_string(&repair)?, account],
        )? == 1,
        "repair scope changed",
    )?;
    Ok(())
}

fn worker(
    seed: &Path,
    output: &Path,
    mode: &str,
    fault: &str,
    storage: Option<&Path>,
) -> Result<()> {
    check(
        ["sensitive", "insensitive"].contains(&mode),
        "invalid casing mode",
    )?;
    check(
        ["uncommitted", "commit-before-ack", "sqlite-full", "enospc"].contains(&fault),
        "invalid fault",
    )?;
    check(
        load_json(&seed.join("result.json"))?["Format"] == "ifw-rw02-sqlite-assessment-v1",
        "not the reviewed synthetic seed",
    )?;
    std::fs::create_dir(output)?;
    let seed_database = Connection::open_with_flags(
        seed.join(format!("{mode}.backup.db")),
        OpenFlags::SQLITE_OPEN_READ_ONLY,
    )?;
    check(
        (fault == "enospc") == storage.is_some(),
        "ENOSPC requires the explicit private tmpfs directory",
    )?;
    let database_directory = storage.unwrap_or(output);
    let database_path = database_directory.join("state.db");
    backup(&seed_database, &database_path)?;
    drop(seed_database);
    let mut database = Connection::open(&database_path)?;
    check(
        database.query_row::<String, _, _>("SELECT sqlite_source_id()", [], |row| row.get(0))?
            == SOURCE_ID,
        "unreviewed SQLite source",
    )?;
    let compile_options: Vec<String> = database
        .prepare("PRAGMA compile_options")?
        .query_map([], |row| row.get(0))?
        .collect::<rusqlite::Result<_>>()?;
    check(
        compile_options.contains(&"OMIT_LOAD_EXTENSION".to_owned())
            && !compile_options.contains(&"ENABLE_LOAD_EXTENSION".to_owned()),
        "extension loading gate failed",
    )?;
    reviewed::fault_initialize_wal(&database)?;
    database
        .execute_batch("PRAGMA synchronous=FULL; PRAGMA cache_size=8; PRAGMA cache_spill=ON;")?;
    check(
        database.pragma_query_value::<String, _>(None, "journal_mode", |row| row.get(0))? == "wal",
        "WAL not active",
    )?;
    check(
        database.pragma_query_value::<i64, _>(None, "synchronous", |row| row.get(0))? == 2,
        "synchronous FULL not active",
    )?;
    let baseline = reviewed::fault_snapshot(&database)?;
    let mut confirmed = expected_state(
        load_json(&seed.join(format!("{mode}.expected.json")))?,
        false,
    )?;
    let main_before = digest(&database_path)?;
    {
        let transaction = database.transaction()?;
        update_four_tables(&transaction, &confirmed, false)?;
        transaction.commit()?;
    }
    confirmed["Snapshot"] = reviewed::fault_snapshot(&database)?;
    check(
        confirmed["Snapshot"] != baseline,
        "confirmation had no durable logical change",
    )?;
    check(
        digest(&database_path)? == main_before,
        "confirmed update was not exclusive to live WAL",
    )?;
    let wal = database_directory.join("state.db-wal");
    let confirmed_wal = std::fs::metadata(&wal)?.len();
    check(confirmed_wal > 32, "confirmed WAL has no frames")?;
    let snapshot_path = output.join("snapshot.db");
    let snapshot_sha256 = backup(&database, &snapshot_path)?;
    write_json(&output.join("confirmed.expected.json"), &confirmed)?;
    emit(
        &json!({"phase":"confirmed", "commit_returned":true, "wal_bytes":confirmed_wal,
        "snapshot_sha256":snapshot_sha256}),
    )?;
    let mut pending = expected_state(confirmed.clone(), true)?;
    let page_size: i64 = database.pragma_query_value(None, "page_size", |row| row.get(0))?;
    let page_count: i64 = database.pragma_query_value(None, "page_count", |row| row.get(0))?;
    let cap = if fault == "sqlite-full" {
        database.pragma_update(None, "max_page_count", page_count + 16)?;
        let actual: i64 = database.pragma_query_value(None, "max_page_count", |row| row.get(0))?;
        check(
            actual == page_count + 16 && actual * page_size < PAYLOAD_BYTES as i64,
            "SQLite page limit was not bounded",
        )?;
        Some(actual)
    } else {
        None
    };
    let sqlite_max_pages: i64 =
        database.pragma_query_value(None, "max_page_count", |row| row.get(0))?;
    let mut os_full = Value::Null;
    let filler_path = database_directory.join("space-filler.bin");
    if fault == "enospc" {
        check(
            sqlite_max_pages * page_size > 16 * 1024 * 1024,
            "unexpected logical SQLite capacity limit",
        )?;
        let mut filler = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&filler_path)?;
        let buffer = [0x5a_u8; 65536];
        let mut observed_error = None;
        // The namespace must be 8 MiB; this independent ceiling prevents a
        // missing tmpfs mount from filling an ordinary filesystem.
        for _ in 0..256 {
            match filler.write_all(&buffer) {
                Ok(()) => {}
                Err(error) => {
                    observed_error = error.raw_os_error();
                    break;
                }
            }
        }
        check(
            observed_error == Some(28),
            "bounded filler did not encounter actual OS ENOSPC",
        )?;
        os_full = json!({"errno":observed_error, "filler_bytes":filler.metadata()?.len(), "maximum_attempted_bytes":16777216});
        drop(filler);
    }
    let transaction = database.transaction()?;
    let update = update_four_tables(&transaction, &pending, true);
    if fault == "sqlite-full" || fault == "enospc" {
        let error = update.err().ok_or("SQLITE_FULL was not triggered")?;
        let sql_error = error
            .downcast_ref::<rusqlite::Error>()
            .ok_or("not a SQLite failure")?;
        check(
            sql_error.sqlite_error_code() == Some(rusqlite::ErrorCode::DiskFull),
            "write failure was not SQLITE_FULL",
        )?;
        let extended = sql_error
            .sqlite_error()
            .ok_or("missing SQLite error")?
            .extended_code;
        let automatic_rollback = transaction.is_autocommit();
        let dirty_before_drop = reviewed::fault_snapshot(&transaction)? != confirmed["Snapshot"];
        drop(transaction);
        check(
            reviewed::fault_snapshot(&database)? == confirmed["Snapshot"],
            "SQLITE_FULL left partial data",
        )?;
        integrity(&database)?;
        let mut evidence = json!({"format":"ifw-storage-fault-v1", "mode":mode, "fault":fault,
            "snapshot_sha256":snapshot_sha256,
            "sqlite_version":rusqlite::version(), "sqlite_source_id":SOURCE_ID, "compile_options":compile_options,
            "page_size":page_size, "page_count_before":page_count, "max_page_count":cap,
            "database_limit_bytes":cap.map(|pages| pages*page_size), "sqlite_max_page_count":sqlite_max_pages,
            "attempted_payload_bytes":PAYLOAD_BYTES, "operating_system_full":os_full,
            "sqlite_extended_error":extended, "automatic_rollback":automatic_rollback,
            "uncommitted_changes_before_drop":dirty_before_drop,
            "rollback_action":"rusqlite Transaction Drop before further work",
            "confirmed_wal_bytes":confirmed_wal, "integrity_check":"ok", "result":"confirmed-only",
            "failure_mechanism":if fault == "enospc" {"OS ENOSPC on a private bounded tmpfs"} else {"SQLite max_page_count; not filesystem ENOSPC"}});
        if fault == "enospc" {
            let capture = output.join("at-full-before-release");
            std::fs::create_dir(&capture)?;
            for suffix in ["", "-wal", "-shm"] {
                let name = format!("state.db{suffix}");
                let source = database_directory.join(&name);
                if source.exists() {
                    std::fs::copy(source, capture.join(name))?;
                }
            }
            emit(
                &json!({"phase":"enospc-observed", "os_errno":28, "sqlite_extended_error":extended,
                    "snapshot_sha256":authenticate_snapshot(&snapshot_path, &snapshot_sha256)?}),
            )?;
            let mut acknowledgement = String::new();
            io::stdin().read_line(&mut acknowledgement)?;
            check(
                acknowledgement == "release-space\n",
                "namespace did not confirm full tmpfs",
            )?;
            std::fs::remove_file(&filler_path)?;
            drop(database);
            let snapshot_copy_path = database_directory.join("restore-source.db");
            snapshot_copy(&snapshot_path, &snapshot_copy_path, &snapshot_sha256)?;
            let snapshot =
                Connection::open_with_flags(&snapshot_copy_path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
            let recovered_path = database_directory.join("same-volume-restored.db");
            backup(&snapshot, &recovered_path)?;
            let recovered = Connection::open(&recovered_path)?;
            integrity(&recovered)?;
            check(
                reviewed::fault_snapshot(&recovered)? == confirmed["Snapshot"],
                "same-tmpfs backup restore differed",
            )?;
            drop(recovered);
            drop(snapshot);
            authenticate_snapshot(&snapshot_path, &snapshot_sha256)?;
            std::fs::copy(recovered_path, output.join("same-volume-restored.db"))?;
            for suffix in ["", "-wal", "-shm"] {
                let name = format!("state.db{suffix}");
                let source = database_directory.join(&name);
                if source.exists() {
                    std::fs::copy(source, output.join(name))?;
                }
            }
            evidence["same_volume_backup_restore"] = json!(true);
            evidence["only_owned_filler_removed"] = json!(true);
            evidence["same_volume_source_sha256"] = json!(snapshot_sha256);
        }
        authenticate_snapshot(&snapshot_path, &snapshot_sha256)?;
        write_json(&output.join("fault.json"), &evidence)?;
        emit(
            &json!({"phase":"sqlite-full", "sqlite_extended_error":extended,
            "snapshot_sha256":snapshot_sha256}),
        )?;
        return Ok(());
    }
    update?;
    let live = reviewed::fault_snapshot(&transaction)?;
    check(
        live != confirmed["Snapshot"],
        "uncommitted four-table state did not differ",
    )?;
    let pending_wal = std::fs::metadata(&wal)?.len();
    check(
        pending_wal > confirmed_wal + 4096,
        "uncommitted pages were not spilled into WAL",
    )?;
    let committed = fault == "commit-before-ack";
    if committed {
        transaction.commit()?;
        pending["Repairs"][0]["FaultExperimentPayload"] = json!("x".repeat(PAYLOAD_BYTES));
        pending["Snapshot"] = reviewed::fault_snapshot(&database)?;
        write_json(&output.join("unacknowledged.expected.json"), &pending)?;
    } else {
        // Keep the transaction alive until the parent kills this process. Its
        // destructor must not run; graceful exit would only exercise rollback.
        std::mem::forget(transaction);
    }
    let evidence = json!({"format":"ifw-storage-fault-v1", "mode":mode, "fault":fault,
        "snapshot_sha256":snapshot_sha256,
        "sqlite_version":rusqlite::version(), "sqlite_source_id":SOURCE_ID, "compile_options":compile_options,
        "confirmed_wal_bytes":confirmed_wal, "pending_wal_bytes":pending_wal,
        "page_size":page_size, "attempted_payload_bytes":PAYLOAD_BYTES,
        "pending_commit_returned":committed, "pending_application_acknowledged":false,
        "expected_recovery":if committed {"unacknowledged-committed"} else {"confirmed-only"}});
    write_json(&output.join("fault.json"), &evidence)?;
    emit(
        &json!({"phase":"kill-ready", "pending_commit_returned":committed, "wal_bytes":std::fs::metadata(&wal)?.len(),
            "snapshot_sha256":authenticate_snapshot(&snapshot_path, &snapshot_sha256)?}),
    )?;
    // A bounded parent timeout kills this exact owned child, including on error.
    loop {
        std::thread::park();
    }
}

fn verify(output: &Path, producer_sha256: &str) -> Result<()> {
    let snapshot_path = output.join("snapshot.db");
    // Fail before any SQLite open or derived file, including in negative trials.
    let before_sha256 = authenticate_snapshot(&snapshot_path, producer_sha256)?;
    let case = load_json(&output.join("fault.json"))?;
    check(
        case["format"] == "ifw-storage-fault-v1",
        "wrong fault profile",
    )?;
    check(
        case["snapshot_sha256"] == producer_sha256,
        "fault marker changed producer digest",
    )?;
    let recovery = if case["fault"] == "commit-before-ack" {
        "unacknowledged.expected.json"
    } else {
        "confirmed.expected.json"
    };
    let expected = load_json(&output.join(recovery))?;
    let database =
        Connection::open_with_flags(output.join("state.db"), OpenFlags::SQLITE_OPEN_READ_WRITE)?;
    integrity(&database)?;
    let actual = reviewed::fault_snapshot(&database)?;
    check(
        actual == expected["Snapshot"],
        "recovered state is partial or lost a confirmed transaction",
    )?;
    drop(database);
    let copy_path = output.join("rust-snapshot.db");
    snapshot_copy(&snapshot_path, &copy_path, producer_sha256)?;
    let snapshot = Connection::open_with_flags(&copy_path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let confirmed = load_json(&output.join("confirmed.expected.json"))?;
    check(
        reviewed::fault_snapshot(&snapshot)? == confirmed["Snapshot"],
        "retained pre-fault snapshot changed",
    )?;
    backup(&snapshot, &output.join("restored.db"))?;
    let mut restored = Connection::open(output.join("restored.db"))?;
    integrity(&restored)?;
    {
        let transaction = restored.transaction()?;
        check(
            transaction.execute(
                "UPDATE sync_account_status SET last_successful_sync_utc=?1 WHERE account_scope=?2",
                params![PENDING_TIME, confirmed["Account"].as_str()],
            )? == 1,
            "restored profile not writable",
        )?;
        transaction.rollback()?;
    }
    check(
        reviewed::fault_snapshot(&restored)? == confirmed["Snapshot"],
        "restore changed data after writable rollback check",
    )?;
    backup(&snapshot, &output.join("negative-control.db"))?;
    let negative = Connection::open(output.join("negative-control.db"))?;
    check(
        negative.execute(
            "UPDATE owned_albums SET album_id=?1 WHERE account_scope=?2",
            params!["album-deliberately-unequal", confirmed["Account"].as_str()],
        )? == 1,
        "negative control did not mutate the actual SQLite row",
    )?;
    integrity(&negative)?;
    check(
        reviewed::fault_snapshot(&negative)? != confirmed["Snapshot"],
        "actual unequal SQLite state escaped snapshot comparison",
    )?;
    drop(snapshot);
    let after_sha256 = authenticate_snapshot(&snapshot_path, producer_sha256)?;
    write_json(
        &output.join("verification.json"),
        &json!({"format":"ifw-storage-fault-verification-v1",
        "recovery_expected":recovery,"integrity_check":"ok", "recovered_full_snapshot_matched":true,
            "restored_full_snapshot_matched":true,"restored_write_rollback_passed":true,"actual_sql_mutation_detected":true,
        "snapshot_sha256":producer_sha256, "snapshot_before_sha256":before_sha256,
        "snapshot_after_sha256":after_sha256, "snapshot_copy_sha256":producer_sha256,
        "os":std::env::consts::OS,"arch":std::env::consts::ARCH}),
    )?;
    println!("Fault recovery and full backup restoration passed");
    Ok(())
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    match args.as_slice() {
        [command, seed, output, mode, fault] if command == "worker" => worker(
            &PathBuf::from(seed), &PathBuf::from(output), mode.to_str().ok_or("mode UTF-8")?, fault.to_str().ok_or("fault UTF-8")?, None,
        ),
        [command, seed, output, mode, fault, storage] if command == "worker" && fault == "enospc" => worker(
            &PathBuf::from(seed), &PathBuf::from(output), mode.to_str().ok_or("mode UTF-8")?, "enospc", Some(&PathBuf::from(storage)),
        ),
        [command, output, expected] if command == "verify" => verify(&PathBuf::from(output), expected.to_str().ok_or("SHA-256 UTF-8")?),
        _ => Err("usage: ifw-storage-faults worker <reviewed-seed> <new-output> <sensitive|insensitive> <uncommitted|commit-before-ack|sqlite-full>; or verify <case> <producer-sha256>".into()),
    }
}
