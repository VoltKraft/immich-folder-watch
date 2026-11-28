//! Exercise legacy updates and concordant new entries only on fresh copies of synthetic C# backups.
#![forbid(unsafe_code)]

use ifw_sqlite_assessment::{
    Fixture, InsertDecision, PathLookup, Result, digest, field, limited, verify_backup,
};
use rusqlite::{Connection, OpenFlags, TransactionBehavior, params};
use serde_json::{Value, json};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
#[cfg(unix)]
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::path::Path;

const NEW_SIZE: i64 = 37;
const ACCOUNT: &str = "ifw-managed-invariant-study";

fn new_directory(path: &Path) -> io::Result<()> {
    #[cfg(unix)]
    {
        fs::DirBuilder::new().mode(0o700).create(path)
    }
    #[cfg(not(unix))]
    {
        fs::create_dir(path)
    }
}

#[cfg(test)]
#[test]
fn study_directory_requires_a_fresh_name_and_an_existing_parent() {
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path =
        std::env::temp_dir().join(format!("ifw-storage-study-{}-{nonce}", std::process::id()));
    new_directory(&path).unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o077, 0);
    }
    assert_eq!(
        new_directory(&path).unwrap_err().kind(),
        io::ErrorKind::AlreadyExists
    );
    assert_eq!(
        new_directory(&path.join("absent").join("copy"))
            .unwrap_err()
            .kind(),
        io::ErrorKind::NotFound
    );
    fs::remove_dir(path).unwrap();
}

fn new_file(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut options = OpenOptions::new();
    options.create_new(true).write(true);
    #[cfg(unix)]
    options.mode(0o600);
    let mut file = options.open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

fn open_copy(copy: &Path) -> Result<Connection> {
    let db = Connection::open_with_flags(
        copy,
        OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )?;
    db.execute_batch("PRAGMA trusted_schema=OFF;")?;
    if db.pragma_query_value(None, "user_version", |r| r.get::<_, i64>(0))? != 1
        || db.pragma_query_value(None, "journal_mode", |r| r.get::<_, String>(0))? != "delete"
    {
        return Err("expected a standalone schema-v1 study copy".into());
    }
    Ok(db)
}

fn update(db: &mut Connection, fixture: &Fixture, query: &Value) -> Result<(Value, usize)> {
    let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let account = field(query, "account")?;
    let old = query["expectedFileSize"]
        .as_i64()
        .ok_or("expected an integer old size")?;
    let mut answers = fixture.inspect(&tx, std::slice::from_ref(query))?;
    let answer = answers.pop().ok_or("missing lookup")?;
    let decision = answer.observation();
    let PathLookup::Existing { key, tables } = answer else {
        return Ok((decision, 0));
    };
    if !tables.contains("sync_entries") || tables.contains("sync_timestamp_repairs") {
        return Ok((json!({"status": "pending-repair"}), 0));
    }
    let stored: i64 = tx.query_row(
        "SELECT file_size FROM sync_entries
         WHERE account_scope=?1 AND source_key=?2 AND relative_path_key=?3",
        params![account, key[0], key[1]],
        |row| row.get(0),
    )?;
    if stored != old {
        return Ok((json!({"status": "stale-size"}), 0));
    }
    if stored == NEW_SIZE {
        return Ok((json!({"status": "unchanged-size"}), 0));
    }
    let rows = tx.execute(
        "UPDATE sync_entries SET file_size=?1
         WHERE account_scope=?2 AND source_key=?3 AND relative_path_key=?4 AND file_size=?5",
        params![NEW_SIZE, account, key[0], key[1], old],
    )?;
    if rows != 1 {
        return Err("expected one existing physical record".into());
    }
    tx.commit()?;
    Ok((decision, rows))
}

fn native_insert(directory: &Path, mode: &str, expected: &str) -> Result<()> {
    let fixture = Fixture::load(directory, mode, expected, false)?;
    if fixture.format != "ifw-qualified-path-key-fixture-v1"
        || !fixture.directory.ends_with("casing-fixtures")
    {
        return Err("expected the native C# writer's original casing-fixtures directory".into());
    }
    let original = fixture.directory.join(format!("{mode}.db"));
    let bytes = limited(File::open(&original)?, 16 * 1024 * 1024)?;
    if digest(&bytes) != expected {
        return Err("donor changed before copying".into());
    }
    let destination = fixture
        .directory
        .with_file_name(format!("native-insert-{mode}"));
    new_directory(&destination)?;
    let copy = destination.join("after.db");
    new_file(&copy, &bytes)?;

    let source = if cfg!(windows) {
        "C:/IfwSynthetic/Temp/../Insert/"
    } else {
        "/IfwSynthetic/Temp/../Insert/"
    };
    let stable = json!({"account":"ifw-casing-primary", "source":source, "relative":"New/Stable-é.jpg", "asset":"asset-native-stable"});
    let mut refused = Value::Null;
    if mode == "insensitive" {
        let dependent = json!({"account": stable["account"], "source":source, "relative":"New/Divergent-ƛ.jpg", "asset":"asset-native-dependent"});
        let mut db = open_copy(&copy)?;
        let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let InsertDecision::Refused(answer) = fixture.insert_new(&tx, &dependent)? else {
            return Err("a profile-dependent new identity was accepted".into());
        };
        let decision = answer.observation();
        tx.rollback()?;
        drop(db);
        verify_backup(&copy, expected)?;
        if decision["status"] != "absent-profile-dependent" {
            return Err("expected a new key with differing historical representations".into());
        }
        refused = json!({"request": dependent, "decision": decision, "after": expected});
    }
    let mut db = open_copy(&copy)?;
    let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
    match fixture.insert_new(&tx, &stable)? {
        InsertDecision::Inserted => tx.commit()?,
        InsertDecision::Refused(answer) => {
            return Err(format!("stable new entry refused: {}", answer.observation()).into());
        }
    }
    drop(db);
    let after = digest(&limited(File::open(&copy)?, 16 * 1024 * 1024)?);
    verify_backup(&copy, &after)?;
    verify_backup(&original, expected)?;
    let receipt = json!({"format":"ifw-native-concordant-insert-v1", "os":std::env::consts::OS,
        "arch":std::env::consts::ARCH, "writerProfile":fixture.writer, "donor":expected, "mode":mode,
        "refused":refused, "stable":stable, "after":after});
    new_file(
        &destination.join("receipt.json"),
        &serde_json::to_vec(&receipt)?,
    )
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if let [flag, dir, mode, expected] = args.as_slice()
        && flag == "--native-insert"
    {
        return native_insert(
            Path::new(dir),
            mode.to_str().ok_or("invalid comparison mode")?,
            expected.to_str().ok_or("invalid digest")?,
        );
    }
    let (dir, mode, expected, destination, control) = match args.as_slice() {
        [dir, mode, expected, destination] => (dir, mode, expected, destination, false),
        [flag, dir, mode, expected, destination] if flag == "--unexplained-control" => {
            (dir, mode, expected, destination, true)
        }
        _ => return Err("usage: update_study_copy [--unexplained-control] <frozen-writer> <mode> <snapshot-sha256> <fresh-directory>".into()),
    };
    let mode = mode.to_str().ok_or("invalid comparison mode")?;
    let expected = expected.to_str().ok_or("invalid digest")?;
    let fixture = Fixture::load(Path::new(dir), mode, expected, true)?;
    let source = fixture.directory.join(format!("{mode}.db"));
    let query: Value = serde_json::from_slice(&limited(std::io::stdin().lock(), 32_768)?)?;
    let destination = Path::new(destination);
    let scratch = fs::canonicalize("artifacts/rust")?.join("stored-key-mutations");
    let parent = destination.parent().ok_or("missing output parent")?;
    if parent != fs::canonicalize(parent)?
        || !parent.starts_with(&scratch)
        || destination.starts_with(&fixture.directory)
        || destination.file_name().is_none()
    {
        return Err(
            "expected a fresh directory under the separate stored-key-mutations area".into(),
        );
    }
    let bytes = limited(File::open(&source)?, 16 * 1024 * 1024)?;
    if digest(&bytes) != expected {
        return Err("donor changed before copying".into());
    }
    new_directory(destination)?;
    let copy = destination.join("after.db");
    new_file(&copy, &bytes)?;
    if control {
        // This deliberately damages a different row only while constructing the negative fixture.
        // The update below sees the completed negative fixture through the ordinary lookup.
        let db = open_copy(&copy)?;
        let rows = db.execute(
            "UPDATE sync_entries SET relative_path_key='!ifw-derived-control!'
                    WHERE account_scope=? AND relative_path='sharp-s-ß.jpg'",
            [ACCOUNT],
        )?;
        if rows != 1 {
            return Err("expected one synthetic negative control row".into());
        }
    }
    let before = destination.join("before.db");
    let bytes = limited(File::open(&copy)?, 16 * 1024 * 1024)?;
    let before_sha = digest(&bytes);
    new_file(&before, &bytes)?;
    verify_backup(&copy, &before_sha)?;
    let (decision, rows) = update(&mut open_copy(&copy)?, &fixture, &query)?;
    let after_sha = digest(&limited(File::open(&copy)?, 16 * 1024 * 1024)?);
    let mut repeat = Value::Null;
    if rows == 1 {
        let mut at_target = query.clone();
        at_target["expectedFileSize"] = NEW_SIZE.into();
        let (observed, changed) = update(&mut open_copy(&copy)?, &fixture, &at_target)?;
        if observed["status"] != "unchanged-size" || changed != 0 {
            return Err("an exact retry at the stored target size changed the copy".into());
        }
        repeat =
            json!({"expectedFileSize": NEW_SIZE, "decision": observed, "rowsChanged": changed});
    }
    verify_backup(&copy, &after_sha)?;
    verify_backup(&before, &before_sha)?;
    verify_backup(&source, expected)?;
    if rows == 0 && before_sha != after_sha {
        return Err("refused update changed its input".into());
    }
    let receipt = json!({"format":"ifw-study-file-size-update-v1", "writerProfile":fixture.writer, "request":query,
        "writerReceiptSha256":fixture.study_receipt, "donorSha256":expected, "mode":mode,
        "preparedUnexplainedControl":control, "beforeSha256":before_sha, "afterSha256":after_sha,
        "decision":decision, "rowsChanged":rows, "replacementFileSize":NEW_SIZE, "repeatAtTarget":repeat});
    serde_json::to_writer(std::io::stdout().lock(), &receipt)?;
    Ok(())
}
