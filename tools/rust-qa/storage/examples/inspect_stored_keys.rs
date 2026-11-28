//! Read previously stored identities in a finalized, synthetic C# SQLite backup.
#![forbid(unsafe_code)]

use ifw_sqlite_assessment::{Fixture, Result, limited, verify_backup};
use rusqlite::{Connection, OpenFlags};
use serde_json::{Value, json};
use std::path::Path;

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let (directory, mode, expected, study) = match args.as_slice() {
        [directory, mode, expected] => (directory, mode, expected, false),
        [flag, directory, mode, expected] if flag == "--three-profile-study" => (directory, mode, expected, true),
        _ => return Err("usage: inspect_stored_keys [--three-profile-study] <synthetic-backup-directory> <mode> <snapshot-sha256>".into()),
    };
    let mode = mode.to_str().ok_or("invalid comparison mode")?;
    let expected = expected.to_str().ok_or("invalid digest")?;
    let fixture = Fixture::load(Path::new(directory), mode, expected, study)?;
    std::env::set_current_dir(&fixture.directory)?;
    let filename = format!("{mode}.db");
    // Only these fixed filenames are used in a URI. The fixture owns the completed backup.
    let uri = format!("file:{filename}?mode=ro&immutable=1");
    let db = Connection::open_with_flags(
        uri,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_URI,
    )?;
    db.execute_batch("PRAGMA query_only=ON; PRAGMA trusted_schema=OFF;")?;
    let version: i64 = db.pragma_query_value(None, "user_version", |row| row.get(0))?;
    if version != 1 {
        return Err("expected a completed schema-v1 reference backup".into());
    }
    let queries: Vec<Value> =
        serde_json::from_slice(&limited(std::io::stdin().lock(), 1024 * 1024)?)?;
    let observations: Vec<_> = fixture
        .inspect(&db, &queries)?
        .iter()
        .map(|answer| answer.observation())
        .collect();
    // These tables contain no original pair of displayed paths. Their values never grant a lookup.
    let ownership: i64 = db.query_row("SELECT count(*) FROM owned_albums", [], |row| row.get(0))?;
    let history: i64 = db.query_row("SELECT count(*) FROM sync_account_status", [], |row| {
        row.get(0)
    })?;
    drop(db);
    verify_backup(Path::new(&filename), expected)?;
    let mut output = json!({
        "format": "ifw-stored-path-key-observations-v1", "inputFormat": fixture.format, "mode": mode, "snapshotSha256": expected,
        "writerProfile": fixture.writer,
        "os": std::env::consts::OS, "arch": std::env::consts::ARCH, "lookup": observations,
        "opaqueOwnershipRows": ownership, "transferHistoryRows": history,
    });
    if let Some(receipt) = fixture.study_receipt {
        output["writerReceiptSha256"] = json!(receipt);
    }
    serde_json::to_writer(std::io::stdout().lock(), &output)?;
    Ok(())
}
