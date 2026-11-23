//! Distinguish a valid pre-activity donor from the tombstone or interrupted journal the worker needs.
use super::{Result, Transfer, check_source, digest, single_row};
use ifw_legacy::timestamp::UtcTicks;
use rusqlite::{Connection, params};
use serde_json::{Value, json};

const CREATED: &str = "2004-02-04T06:08:10.0000000+00:00";
const MODIFIED: &str = "2004-02-06T06:08:10.0000000+00:00";
const TRANSFER_TIME: &str = "2014-02-04T06:08:10.0000000+00:00";
const ACCOUNT_TIME: &str = "2014-02-05T06:08:10.0000000+00:00";

struct Mapping {
    source: String,
    key: String,
    modified: String,
    status: i64,
    synchronized: String,
    expires: Option<String>,
    history: String,
}

pub(super) fn check_transition(
    before: &Connection,
    latest: &Connection,
    kind: Transfer,
) -> Result<()> {
    // The tombstone changes only status, synchronization time and expiry. A pending
    // timestamp correction preserves the entire original entry until completion.
    let mapping = if kind == Transfer::Deletion {
        "SELECT account_scope,source_path,source_key,relative_path,relative_path_key,asset_id,
                album_name,file_size,last_write_time_utc,direction FROM sync_entries"
    } else {
        "SELECT * FROM sync_entries"
    };
    for sql in [mapping, "SELECT * FROM sync_account_status"] {
        if single_row(before, sql)? != single_row(latest, sql)? {
            return Err(
                "rollback donor belongs to a different original mapping or account history".into(),
            );
        }
    }
    Ok(())
}

pub(super) fn ready(db: &Connection, counts: [i64; 4], kind: Transfer) -> Result<bool> {
    let account = digest(b"https://immich.example/api\ntest-key");
    let (asset, length) = match kind {
        Transfer::Deletion if counts == [0, 1, 1, 0] => (
            format!(
                "asset-{}",
                digest(&[0xff, 0xd8, 0, 0x23, 0x7f, 0x80, 0xfe, 0xff, 0xd9])
            ),
            9,
        ),
        Transfer::Repair if counts == [0, 1, 1, 0] || counts == [0, 1, 1, 1] => {
            ("remote".to_owned(), 6)
        }
        _ => return Err("unexpected rows for the requested rollback activity".into()),
    };
    let relative_key = if cfg!(windows) {
        "PHOTO.JPG"
    } else {
        "photo.jpg"
    };
    let entry = db.query_one(
        "SELECT e.source_path,e.source_key,e.last_write_time_utc,e.status,e.last_synchronized_at_utc,
                e.tombstone_expires_at_utc,a.last_successful_sync_utc
         FROM sync_entries AS e JOIN sync_account_status AS a USING(account_scope)
         WHERE e.account_scope=?1 AND e.relative_path='photo.jpg' AND e.relative_path_key=?2
           AND e.asset_id=?3 AND e.album_name='Camera' AND e.file_size=?4 AND e.direction=1",
        params![account, relative_key, asset, length],
        |r| Ok(Mapping { source:r.get(0)?, key:r.get(1)?, modified:r.get(2)?, status:r.get(3)?,
                         synchronized:r.get(4)?, expires:r.get(5)?, history:r.get(6)? }),
    )?;
    check_source(&entry.source)?;
    #[cfg(windows)]
    let key = ifw_legacy::casing::ReferenceCaseMap::from_reference_tsv(include_str!(
        "../../../legacy/casing/unicode-15.1.0.tsv"
    ))?
    .uppercase(&entry.source);
    #[cfg(not(windows))]
    let key = entry.source.clone();
    if entry.key != key {
        return Err("unexpected synthetic watch-root key".into());
    }

    if kind == Transfer::Deletion {
        return deletion_ready(&entry);
    }
    repair_ready(db, &entry, &account, relative_key, counts[3] == 1)
}

fn deletion_ready(entry: &Mapping) -> Result<bool> {
    if entry.modified != CREATED {
        return Err("incorrect original deletion timestamp".into());
    }
    let transfer = UtcTicks::parse_sql(&entry.synchronized)?;
    let history = UtcTicks::parse_sql(&entry.history)?;
    match (entry.status, entry.expires.as_deref()) {
        (0, None) if transfer <= history => Ok(false),
        (1, Some(expiry)) if history <= transfer && transfer < UtcTicks::parse_sql(expiry)? => {
            Ok(true)
        }
        _ => Err("inconsistent tombstone status, expiry or Last Sync".into()),
    }
}

fn repair_ready(
    db: &Connection,
    entry: &Mapping,
    account: &str,
    relative_key: &str,
    has_journal: bool,
) -> Result<bool> {
    let desired = if cfg!(windows) { MODIFIED } else { CREATED };
    let modified = UtcTicks::parse_sql(&entry.modified)?;
    if entry.status != 0
        || entry.expires.is_some()
        || entry.synchronized != TRANSFER_TIME
        || entry.history != ACCOUNT_TIME
        || entry.modified == desired
    {
        return Err("wrong mapping or account history for the interrupted repair".into());
    }
    if !has_journal {
        return Ok(false);
    }
    let payload: String = db.query_one(
        "SELECT repair_json FROM sync_timestamp_repairs WHERE account_scope=?1 AND source_key=?2 AND relative_path_key=?3",
        params![account,entry.key,relative_key], |r| r.get(0),
    )?;
    let expected = json!({
        "OriginalEntry":{
            "AccountScope":account,"SourcePath":entry.source,"RelativePath":"photo.jpg","AssetId":"remote",
            "AlbumName":"Camera","FileSize":6,"LastWriteTimeUtc":modified.format_json_utc_scalar(),"Direction":1,"Status":0,
            "LastSynchronizedAtUtc":UtcTicks::parse_sql(TRANSFER_TIME)?.format_json_utc_scalar(),"TombstoneExpiresAtUtc":null
        },
        "CreationTimeUtc":UtcTicks::parse_sql(CREATED)?.format_json_utc_scalar(),
        "LastWriteTimeUtc":UtcTicks::parse_sql(desired)?.format_json_utc_scalar(),
        "ContentSha256":digest(b"remote").to_ascii_uppercase()
    });
    if serde_json::from_str::<Value>(&payload)? != expected {
        return Err(
            "repair journal differs from the original mapping, timestamps or media digest".into(),
        );
    }
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{GOLDEN, canonical_catalog, catalog, read_activity};

    fn profile(kind: Transfer, run: u32) -> Result<Connection> {
        let db = Connection::open_in_memory()?;
        db.execute_batch(GOLDEN)?;
        db.execute_batch(
            "DELETE FROM owned_albums; DELETE FROM sync_account_status;
                          DELETE FROM sync_timestamp_repairs; DELETE FROM sync_entries;",
        )?;
        let base = if cfg!(windows) {
            r"C:\ifw-synthetic"
        } else {
            "/ifw-synthetic"
        };
        let source = std::path::Path::new(base)
            .join(format!("immich-folder-watch-worker-tests-{run:032x}"))
            .join("watch");
        let source = source.to_str().ok_or("invalid synthetic path")?;
        let key = if cfg!(windows) {
            source.to_ascii_uppercase()
        } else {
            source.to_owned()
        };
        let relative = if cfg!(windows) {
            "PHOTO.JPG"
        } else {
            "photo.jpg"
        };
        let (asset, length, modified) = match kind {
            Transfer::Deletion => (
                "asset-4cc68536d5276471e459b00eb73cc9f22e2cfe97bbb5c2c1a72365bfffee437a",
                9,
                CREATED,
            ),
            Transfer::Repair => ("remote", 6, "2000-01-02T03:04:05.0000000+00:00"),
            _ => return Err("expected a rollback fixture".into()),
        };
        let account = digest(b"https://immich.example/api\ntest-key");
        db.execute(
            "INSERT INTO sync_account_status VALUES (?1,?2)",
            params![account, ACCOUNT_TIME],
        )?;
        db.execute("INSERT INTO sync_entries VALUES (?1,?2,?3,'photo.jpg',?4,?5,'Camera',?6,?7,1,0,?8,NULL)",
                   params![account,source,key,relative,asset,length,modified,TRANSFER_TIME])?;
        Ok(db)
    }

    fn record_activity(db: &Connection, kind: Transfer) -> Result<()> {
        if kind == Transfer::Deletion {
            db.execute("UPDATE sync_entries SET status=1,last_synchronized_at_utc=?1,tombstone_expires_at_utc=?2",
                       [ACCOUNT_TIME, "2014-02-12T06:08:10.0000000+00:00"])?;
        } else {
            let desired = if cfg!(windows) {
                "2004-02-06"
            } else {
                "2004-02-04"
            };
            db.execute(
                "INSERT INTO sync_timestamp_repairs SELECT account_scope,source_key,relative_path_key,
                 json_object('OriginalEntry',json_object('AccountScope',account_scope,'SourcePath',source_path,
                 'RelativePath',relative_path,'AssetId',asset_id,'AlbumName',album_name,'FileSize',file_size,
                 'LastWriteTimeUtc','2000-01-02T03:04:05+00:00','Direction',direction,'Status',status,
                 'LastSynchronizedAtUtc','2014-02-04T06:08:10+00:00','TombstoneExpiresAtUtc',NULL),
                 'CreationTimeUtc','2004-02-04T06:08:10+00:00','LastWriteTimeUtc',?1,'ContentSha256',?2)
                 FROM sync_entries", params![format!("{desired}T06:08:10+00:00"),digest(b"remote").to_ascii_uppercase()])?;
        }
        Ok(())
    }

    #[test]
    fn qualified_donors_from_different_worker_runs_cannot_be_paired() -> Result<()> {
        for kind in [Transfer::Deletion, Transfer::Repair] {
            let before = profile(kind, 1)?;
            let latest = profile(kind, 1)?;
            let unrelated = profile(kind, 2)?;
            let schema = canonical_catalog(catalog(&before)?);
            assert!(read_activity(&before, &schema, kind)?.is_none());
            for db in [&latest, &unrelated] {
                record_activity(db, kind)?;
                assert!(read_activity(db, &schema, kind)?.is_some());
            }
            check_transition(&before, &latest, kind)?;
            assert!(check_transition(&before, &unrelated, kind).is_err());
        }
        Ok(())
    }

    #[test]
    fn an_interrupted_journal_must_still_describe_its_original_mapping() -> Result<()> {
        let db = profile(Transfer::Repair, 1)?;
        let schema = canonical_catalog(catalog(&db)?);
        record_activity(&db, Transfer::Repair)?;
        assert!(read_activity(&db, &schema, Transfer::Repair)?.is_some());
        db.execute(
            "UPDATE sync_timestamp_repairs SET repair_json=json_set(repair_json,
                    '$.OriginalEntry.LastWriteTimeUtc','2000-01-03T03:04:05+00:00')",
            [],
        )?;
        assert!(read_activity(&db, &schema, Transfer::Repair).is_err());
        Ok(())
    }
}
