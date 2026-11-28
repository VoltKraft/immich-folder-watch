//! Development-only synthetic storage assessment, not an application adapter.
#![forbid(unsafe_code)]

mod preflight;
mod wal_preflight_cases;

use ifw_legacy::timestamp::UtcTicks;
use rusqlite::backup::Backup;
use rusqlite::types::ValueRef;
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::error::Error;
use std::fmt;
use std::path::{Path, PathBuf};
use std::time::Duration;

type Result<T> = std::result::Result<T, Box<dyn Error>>;
const TABLES: [&str; 4] = [
    "owned_albums",
    "sync_account_status",
    "sync_entries",
    "sync_timestamp_repairs",
];
const CHANGED_TIME: &str = "2025-01-02T03:04:05.1234567+00:00";
const REPAIR_TIME: &str = "1900-01-02T03:04:05.0000001+00:00";
const SQLITE_VERSION: &str = "3.54.1";
const SQLITE_SOURCE: &str =
    "2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76";

#[derive(Debug)]
struct UnsupportedSchema(i64);

impl fmt::Display for UnsupportedSchema {
    fn fmt(&self, writer: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(writer, "unsupported storage assessment schema {}", self.0)
    }
}

impl Error for UnsupportedSchema {}

fn main() -> Result<()> {
    let arguments: Vec<_> = std::env::args_os().skip(1).collect();
    if arguments.len() != 2 {
        return Err("usage: ifw-sqlite-assessment <native-fixture-directory> <new-isolated-output-directory>".into());
    }
    let fixtures = PathBuf::from(&arguments[0]);
    let output = PathBuf::from(&arguments[1]);
    let manifest: Value = serde_json::from_slice(&std::fs::read(fixtures.join("manifest.json"))?)?;
    ensure(
        manifest["Format"] == "ifw-rw01-legacy-v1"
            && manifest["SyntheticOnly"] == true
            && manifest["Platform"] == std::env::consts::OS,
        "wrong native platform or non-synthetic corpus",
    )?;
    ensure(
        rusqlite::version() == SQLITE_VERSION,
        "wrong SQLite version",
    )?;
    // Refuse an existing profile or prior output; all mutation is in this new tree.
    std::fs::create_dir(&output)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&output, std::fs::Permissions::from_mode(0o700))?;
    }
    let mut cases = Vec::new();
    for mode in ["sensitive", "insensitive"] {
        cases.push(exercise_database(&fixtures, &output, mode)?);
    }
    let identities: Value =
        serde_json::from_slice(&std::fs::read(fixtures.join("identities.json"))?)?;
    let accounts = identities["Accounts"]
        .as_array()
        .ok_or("missing account vectors")?;
    for account in accounts {
        let server = account["ServerApiUrl"]
            .as_str()
            .ok_or("missing URL")?
            .trim()
            .trim_end_matches('/');
        let key = account["ApiKey"].as_str().ok_or("missing synthetic key")?;
        let digest = hex(&Sha256::digest(format!("{server}\n{key}").as_bytes()));
        ensure(
            digest == account["AccountScope"].as_str().unwrap(),
            "C# SHA-256 account identity mismatch",
        )?;
    }
    ensure(
        accounts[0]["AccountScope"] != accounts[3]["AccountScope"],
        "space-sensitive key control",
    )?;
    let report = json!({
        "Format":"ifw-rw02-sqlite-assessment-v1", "Os":std::env::consts::OS, "Arch":std::env::consts::ARCH,
        "SQLiteVersion":rusqlite::version(), "SQLiteSourceId":SQLITE_SOURCE,
        "Cases":cases, "AccountHashVectors":accounts.len(),
        "QuiescentWalPreflight":wal_preflight_cases::run(&output)?,
        "FinalizedRollbackJournal":wal_preflight_cases::persistent_journal(&output)?,
        "ReadOnlyExisting":wal_preflight_cases::read_only_database(&output)?,
        "Unproven":["production migration adapter", "old optional schema repair", "exclusion of a live legacy writer",
            "full disk and process-crash recovery", "YAML", "device identities", "other native targets"]
    });
    std::fs::write(
        output.join("result.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    println!(
        "SQLite assessment passed: two casing modes, four tables, writes, rollback, live WAL backup, quiescent schema preflight and five account hashes."
    );
    Ok(())
}

fn ensure(condition: bool, message: &str) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(message.into())
    }
}

fn exercise_database(fixtures: &Path, output: &Path, mode: &str) -> Result<Value> {
    let sql = std::fs::read_to_string(fixtures.join("sqlite").join(format!("{mode}.sql")))?;
    let mut expected: Value = serde_json::from_slice(&std::fs::read(
        fixtures
            .join("sqlite")
            .join(format!("{mode}.expected.json")),
    )?)?;
    let account = expected["Account"]
        .as_str()
        .ok_or("missing synthetic account")?
        .to_owned();
    let path = output.join(format!("{mode}.db"));
    // Create the synthetic C# corpus, then use the ordinary existing-profile entry point.
    Connection::open(&path)?.execute_batch(&sql)?;
    let mut database = preflight::open_existing(&path, &output.join("preflight"))?;
    ensure(
        database.query_row::<String, _, _>("SELECT sqlite_source_id()", [], |row| row.get(0))?
            == SQLITE_SOURCE,
        "wrong SQLite native source identity",
    )?;
    let compile_options: Vec<String> = database
        .prepare("PRAGMA compile_options")?
        .query_map([], |row| row.get(0))?
        .collect::<rusqlite::Result<_>>()?;
    ensure(
        compile_options.contains(&"OMIT_LOAD_EXTENSION".to_owned()),
        "native extension loading was not omitted",
    )?;
    ensure(
        !compile_options.contains(&"ENABLE_LOAD_EXTENSION".to_owned()),
        "conflicting extension-loading options",
    )?;
    ensure(
        database
            .query_row::<String, _, _>(
                "SELECT load_extension('synthetic-do-not-load')",
                [],
                |row| row.get(0),
            )
            .is_err(),
        "SQL extension entry point exists",
    )?;
    ensure(
        canonical_snapshot(snapshot(&database)?)
            == canonical_snapshot(expected["Snapshot"].clone()),
        "Rust SQLite read differs from actual C# snapshot",
    )?;
    let repair_text: String = database.query_row(
        "SELECT repair_json FROM sync_timestamp_repairs WHERE account_scope=?1",
        [&account],
        |row| row.get(0),
    )?;
    let mut repair: Value = serde_json::from_str(&repair_text)?;
    ensure(
        repair == expected["Repairs"][0],
        "Rust repair JSON decoder disagrees with C# reader",
    )?;
    let modified = UtcTicks::parse_sql(CHANGED_TIME)?.format_sql();
    let creation = UtcTicks::parse_sql(REPAIR_TIME)?.format_json_utc_scalar();
    let content_hash = hex(&Sha256::digest(b"RW02-SYNTHETIC-REPAIR-CONTENT")).to_ascii_uppercase();
    repair["CreationTimeUtc"] = json!(creation);
    repair["ContentSha256"] = json!(content_hash);
    let encoded_repair = serde_json::to_string(&repair)?;
    let before_rollback = snapshot(&database)?;
    {
        let transaction = database.transaction()?;
        transaction.execute(
            "UPDATE sync_account_status SET last_successful_sync_utc=?1 WHERE account_scope=?2",
            params![modified, account],
        )?;
        ensure(
            transaction
                .execute(
                    "UPDATE sync_entries SET file_size=-1 WHERE account_scope=?1",
                    [&account],
                )
                .is_err(),
            "constraint failure was not triggered",
        )?;
        // Drop rolls back the preceding valid update as well as the failed statement.
    }
    ensure(
        snapshot(&database)? == before_rollback,
        "failed transaction changed existing data",
    )?;
    let main_before = digest_file(&path)?;
    {
        let transaction = database.transaction()?;
        ensure(transaction.execute("UPDATE sync_entries SET asset_id=?1,file_size=?2,last_synchronized_at_utc=?3 WHERE account_scope=?4 AND relative_path=?5",
            params!["asset-rust-roundtrip", 9_007_199_254_740_995_i64, modified, account, "download.bin"])? == 1, "entry update scope")?;
        ensure(
            transaction.execute(
                "UPDATE owned_albums SET album_id=?1 WHERE account_scope=?2",
                params!["album-rust-roundtrip", account],
            )? == 1,
            "ownership update scope",
        )?;
        ensure(
            transaction.execute(
                "UPDATE sync_account_status SET last_successful_sync_utc=?1 WHERE account_scope=?2",
                params![modified, account],
            )? == 1,
            "history update scope",
        )?;
        ensure(
            transaction.execute(
                "UPDATE sync_timestamp_repairs SET repair_json=?1 WHERE account_scope=?2",
                params![encoded_repair, account],
            )? == 1,
            "repair update scope",
        )?;
        transaction.commit()?;
    }
    ensure(
        digest_file(&path)? == main_before,
        "test requires committed changes still exclusively in WAL",
    )?;
    let wal_path = sidecar(&path, "-wal");
    let wal_bytes = std::fs::metadata(wal_path)?.len();
    ensure(wal_bytes > 32, "live WAL did not contain frames")?;
    let after = snapshot(&database)?;
    ensure(
        after != before_rollback,
        "unequal snapshots were not detected",
    )?;
    let backup_path = output.join(format!("{mode}.backup.db"));
    let mut destination = Connection::open(&backup_path)?;
    {
        let backup = Backup::new(&database, &mut destination)?;
        backup.run_to_completion(2, Duration::from_millis(1), None)?;
    }
    ensure(
        snapshot(&destination)? == after,
        "online backup lost live WAL changes",
    )?;
    ensure(
        destination.query_row::<String, _, _>("PRAGMA integrity_check", [], |row| row.get(0))?
            == "ok",
        "backup integrity check",
    )?;
    drop(destination);
    drop(database);
    for entry in expected["Entries"].as_array_mut().unwrap() {
        if entry["RelativePath"] == "download.bin" {
            entry["AssetId"] = json!("asset-rust-roundtrip");
            entry["FileSize"] = json!(9_007_199_254_740_995_i64);
            entry["LastSynchronizedAtUtc"] = json!(modified);
        }
    }
    expected["Repairs"][0] = repair;
    expected["LastSuccessfulSyncUtc"] = json!(modified);
    expected["OwnedAlbumId"] = json!("album-rust-roundtrip");
    expected["Snapshot"] = after;
    std::fs::write(
        output.join(format!("{mode}.expected.json")),
        serde_json::to_vec_pretty(&expected)?,
    )?;

    let future_path = output.join(format!("{mode}.future.db"));
    {
        let future = Connection::open(&future_path)?;
        future.execute_batch(&sql)?;
        future.pragma_update(None, "user_version", 99)?;
    }
    let future_before = digest_file(&future_path)?;
    let error = preflight::open_existing(&future_path, &output.join("preflight"))
        .err()
        .ok_or("future schema reached WAL setup")?;
    ensure(
        matches!(
            error.downcast_ref::<UnsupportedSchema>(),
            Some(UnsupportedSchema(99))
        ),
        "unexpected error for future schema",
    )?;
    ensure(
        digest_file(&future_path)? == future_before,
        "future DELETE-mode preflight changed bytes",
    )?;
    for suffix in ["-wal", "-shm", "-journal"] {
        ensure(
            !sidecar(&future_path, suffix).exists(),
            "future DELETE-mode preflight created sidecars",
        )?;
    }
    Ok(
        json!({"Mode":mode,"Tables":4,"Rows":9,"InitialCSharpSnapshotMatched":true,"RepairJsonMatched":true,
        "ConstraintRollbackObserved":true,"FourTableWritesCommitted":true,"LiveWalBytes":wal_bytes,
        "MainFileUnchangedBeforeBackup":true,"OnlineBackupContainsCommittedWal":true,"IntegrityCheck":"ok",
        "FutureDeleteModeBytesAndSidecarsUnchanged":true,"FutureInitializerRejectedVersion":99,"CompileOptions":compile_options}),
    )
}

fn digest_file(path: &Path) -> Result<String> {
    Ok(hex(&Sha256::digest(std::fs::read(path)?)))
}

fn sidecar(path: &Path, suffix: &str) -> PathBuf {
    let mut name = path.as_os_str().to_owned();
    name.push(suffix);
    PathBuf::from(name)
}

fn canonical_snapshot(mut value: Value) -> Value {
    if let Some(schema) = value["Schema"].as_array_mut() {
        for object in schema {
            object["Sql"] = json!(object["Sql"].as_str().unwrap().replace("\r\n", "\n"));
        }
    }
    if let Some(tables) = value["Tables"].as_array_mut() {
        for table in tables {
            // The C# snapshot orders sync entries by non-unique source columns;
            // query-plan tie order is not a data contract across SQLite versions.
            table["Rows"]
                .as_array_mut()
                .unwrap()
                .sort_by_key(Value::to_string);
        }
    }
    value
}

fn snapshot(database: &Connection) -> Result<Value> {
    let version: i64 = database.pragma_query_value(None, "user_version", |row| row.get(0))?;
    let mut statement = database.prepare(
        "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type DESC,name",
    )?;
    let schema = statement.query_map([], |row| Ok(json!({"Type":row.get::<_,String>(0)?,"Name":row.get::<_,String>(1)?,"Sql":row.get::<_,String>(2)?})))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let mut tables = Vec::new();
    for table in TABLES {
        // The identifiers are the fixed allowlist above, never external input.
        let mut statement = database.prepare(&format!("SELECT * FROM \"{table}\""))?;
        let columns: Vec<String> = statement.column_names().map(str::to_owned).collect();
        let ordering = (1..=columns.len())
            .map(|index| index.to_string())
            .collect::<Vec<_>>()
            .join(",");
        statement = database.prepare(&format!("SELECT * FROM \"{table}\" ORDER BY {ordering}"))?;
        let rows = statement
            .query_map([], |row| {
                (0..columns.len())
                    .map(|column| {
                        Ok(match row.get_ref(column)? {
                            ValueRef::Null => Value::Null,
                            ValueRef::Integer(value) => json!(value),
                            ValueRef::Text(value) => {
                                json!(std::str::from_utf8(value).map_err(|error| {
                                    rusqlite::Error::FromSqlConversionFailure(
                                        column,
                                        rusqlite::types::Type::Text,
                                        Box::new(error),
                                    )
                                })?)
                            }
                            _ => return Err(rusqlite::Error::InvalidQuery),
                        })
                    })
                    .collect::<rusqlite::Result<Vec<_>>>()
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        tables.push(json!({"Name":table,"Columns":columns,"Rows":rows}));
    }
    Ok(json!({"UserVersion":version,"Schema":schema,"Tables":tables}))
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}
