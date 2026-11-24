//! Insert new entries only on fresh copies of the three frozen Linux x64 C# writer fixtures.
#![forbid(unsafe_code)]

use ifw_sqlite_assessment::{Fixture, PathLookup, Result, digest, field, limited, verify_backup};
use rusqlite::{Connection, OpenFlags, TransactionBehavior, params};
use serde_json::{Value, json};
use std::fs::{self, DirBuilder, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::path::Path;

const PROFILES: [&str; 3] = [
    "02c4363688e37251e1169559be56231d6e9c398ba046ea3773cdf037df72cd2f",
    "51e3c6f44c782e8e99c355b504f32900da56c9e4a500da83a15a2f807b95b6e4",
    "195bd89b3934dcf9c93b72b4232c53d9787dacb8ebbf2270df7a6a73e53f473e",
];
const ACCOUNT: &str = "ifw-managed-invariant-study";
const INSERT: &str = "INSERT INTO sync_entries
    (account_scope,source_path,source_key,relative_path,relative_path_key,asset_id,album_name,
     file_size,last_write_time_utc,direction,status,last_synchronized_at_utc,tombstone_expires_at_utc)
    VALUES (?1,?2,?3,?4,?5,?6,'Synthetic insert',83,'2024-02-29T03:04:05.1234567+00:00',
            1,0,'2024-02-29T03:04:05.1234567+00:00',NULL)";

fn insert_batch(db: &mut Connection, fixture: &Fixture, batch: &Value) -> Result<Value> {
    let rows = batch["entries"]
        .as_array()
        .filter(|v| !v.is_empty() && v.len() <= 32)
        .ok_or("expected between one and 32 requested entries")?;
    let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
    for (index, row) in rows.iter().enumerate() {
        if field(row, "account")? != ACCOUNT {
            return Err("expected the synthetic study account".into());
        }
        let answer = fixture
            .inspect(&tx, std::slice::from_ref(row))?
            .pop()
            .ok_or("missing historical lookup")?;
        let PathLookup::AbsentConcordant { display, key } = answer else {
            tx.rollback()?;
            return Ok(
                json!({"status":"refused", "rowsCommitted":0, "blockedIndex":index, "decision":answer.observation()}),
            );
        };
        if tx.execute(
            INSERT,
            params![
                ACCOUNT,
                display[0],
                key[0],
                display[1],
                key[1],
                field(row, "asset")?
            ],
        )? != 1
        {
            return Err("expected exactly one inserted entry".into());
        }
    }
    tx.commit()?;
    Ok(json!({"status":"inserted", "rowsCommitted":rows.len()}))
}

fn private_mount(path: &str, access: &str) -> Result<()> {
    let mounts = fs::read_to_string("/proc/self/mountinfo")?;
    if mounts
        .lines()
        .filter_map(|line| line.split_once(" - "))
        .any(|(mount, fs)| {
            let cols: Vec<_> = mount.split_whitespace().collect();
            cols.get(4) == Some(&path)
                && cols.get(5).and_then(|options| options.split(',').next()) == Some(access)
                && fs.starts_with("tmpfs ")
        })
    {
        Ok(())
    } else {
        Err("expected the private synthetic mount".into())
    }
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [writer, mode, expected] = args.as_slice() else {
        return Err("expected frozen writer, mode and digest".into());
    };
    if !matches!(writer.as_str(), "older" | "managed" | "current")
        || !matches!(mode.as_str(), "sensitive" | "insensitive")
    {
        return Err("unknown synthetic writer or mode".into());
    }
    let root = Path::new("artifacts/rust/donors");
    let work = Path::new("artifacts/rust/work");
    for (dir, access) in [(root, "ro"), (work, "rw")] {
        private_mount(
            dir.canonicalize()?.to_str().ok_or("invalid mount path")?,
            access,
        )?;
    }
    let plan: Value = serde_json::from_slice(&limited(std::io::stdin().lock(), 65536)?)?;
    if plan["rollbackProfiles"] != json!(PROFILES) {
        return Err("unqualified rollback profile set".into());
    }
    let batches = plan["batches"]
        .as_array()
        .filter(|v| !v.is_empty() && v.len() <= 32)
        .ok_or("invalid batch count")?;
    let donor = root.join(writer);
    let fixture = Fixture::load(&donor, mode, expected, true)?;
    let source = donor.join(format!("{mode}.db"));
    let original = fs::read(&source)?;
    if original.get(18..20) != Some(&[1, 1]) || digest(&original) != *expected {
        return Err("expected the original finalized backup".into());
    }
    let dir = work.join("cases").join(format!("{writer}-{mode}"));
    DirBuilder::new().mode(0o700).create(&dir)?;
    let path = dir.join("after.db");
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&path)?
        .write_all(&original)?;
    let mut outcomes = Vec::new();
    for batch in batches {
        let name = field(batch, "name")?;
        let before = digest(&fs::read(&path)?);
        verify_backup(&path, &before)?;
        let mut db = Connection::open_with_flags(
            &path,
            OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )?;
        db.execute_batch("PRAGMA trusted_schema=OFF")?;
        let sqlite: String = db.query_row("SELECT sqlite_source_id()", [], |row| row.get(0))?;
        let pin: Value = serde_json::from_slice(include_bytes!("../../storage/inputs.json"))?;
        if pin["sqlite"]["source_id"] != sqlite
            || db.pragma_query_value(None, "user_version", |r| r.get::<_, i64>(0))? != 1
        {
            return Err("unexpected SQLite or schema".into());
        }
        let decision = insert_batch(&mut db, &fixture, batch)?;
        drop(db);
        let after = digest(&fs::read(&path)?);
        verify_backup(&path, &after)?;
        if decision["rowsCommitted"] == 0 && before != after {
            return Err("a refused transaction changed its backup".into());
        }
        outcomes.push(json!({"name":name,"before":before,"after":after,"decision":decision}));
    }
    verify_backup(&source, expected)?;
    let report = json!({"format":"ifw-concordant-insert-v1","mode":mode,"writer":fixture.writer,"writerReceipt":fixture.study_receipt,
        "profiles":PROFILES,"donor":expected,"after":digest(&fs::read(path)?),"batches":outcomes});
    fs::write(dir.join("receipt.json"), serde_json::to_vec(&report)?)?;
    Ok(())
}
