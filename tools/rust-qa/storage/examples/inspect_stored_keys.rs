//! Read previously stored identities in a finalized, synthetic C# SQLite backup.
#![forbid(unsafe_code)]

use ifw_legacy::casing::ReferenceCaseMap;
use rusqlite::{Connection, OpenFlags};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fs;
use std::io::{ErrorKind, Read};
use std::path::Path;

type Result<T> = std::result::Result<T, Box<dyn Error>>;
type Key = [String; 2];
const PROFILES: [(&str, &str); 2] = [
    (
        "15.1.0",
        "02c4363688e37251e1169559be56231d6e9c398ba046ea3773cdf037df72cd2f",
    ),
    (
        "17.0.0",
        "195bd89b3934dcf9c93b72b4232c53d9787dacb8ebbf2270df7a6a73e53f473e",
    ),
];

struct Forms {
    maps: Vec<ReferenceCaseMap>,
}

impl Forms {
    fn load(mode: &str) -> Result<Self> {
        let mut maps = Vec::new();
        if mode == "insensitive" {
            for (version, expected) in PROFILES {
                let file = format!("tools/rust-qa/legacy/casing/unicode-{version}.tsv");
                let data = fs::read(file)?;
                if digest(&data) != expected {
                    return Err("unqualified casing input".into());
                }
                maps.push(ReferenceCaseMap::from_reference_tsv(std::str::from_utf8(
                    &data,
                )?)?);
            }
        } else if mode != "sensitive" {
            return Err("an explicit path comparison mode is required".into());
        }
        Ok(Self { maps })
    }

    fn spellings(&self, source: &str, relative: &str) -> Vec<Key> {
        if self.maps.is_empty() {
            return vec![[source.to_owned(), relative.to_owned()]];
        }
        self.maps
            .iter()
            .map(|map| [map.uppercase(source), map.uppercase(relative)])
            .collect()
    }
}

struct Record {
    table: &'static str,
    stored: Key,
    spellings: Vec<Key>,
}

impl Record {
    fn explained(&self) -> bool {
        self.spellings.contains(&self.stored)
    }

    fn accepts_in_every_possible_origin(&self, query: &[Key]) -> bool {
        self.spellings
            .iter()
            .zip(query)
            .all(|(original, requested)| original != &self.stored || requested == &self.stored)
    }
}

type Accounts = BTreeMap<String, Vec<Record>>;

fn field<'a>(value: &'a Value, name: &str) -> Result<&'a str> {
    value
        .get(name)
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
        .ok_or_else(|| "expected a nonempty identity field".into())
}

fn read_records(db: &Connection, forms: &Forms) -> Result<Accounts> {
    let mut accounts = Accounts::new();
    let mut entries = db.prepare("SELECT account_scope,source_key,relative_path_key,source_path,relative_path FROM sync_entries")?;
    let mut cursor = entries.query([])?;
    while let Some(row) = cursor.next()? {
        accounts.entry(row.get(0)?).or_default().push(Record {
            table: "sync_entries",
            stored: [row.get(1)?, row.get(2)?],
            spellings: forms.spellings(row.get_ref(3)?.as_str()?, row.get_ref(4)?.as_str()?),
        });
    }
    let mut repairs = db.prepare(
        "SELECT account_scope,source_key,relative_path_key,repair_json FROM sync_timestamp_repairs",
    )?;
    let mut cursor = repairs.query([])?;
    while let Some(row) = cursor.next()? {
        let account: String = row.get(0)?;
        let repair: Value = serde_json::from_str(row.get_ref(3)?.as_str()?)?;
        let original = &repair["OriginalEntry"];
        if field(original, "AccountScope")? != account {
            return Err("repair identity contradicts its stored account".into());
        }
        accounts.entry(account).or_default().push(Record {
            table: "sync_timestamp_repairs",
            stored: [row.get(1)?, row.get(2)?],
            spellings: forms.spellings(
                field(original, "SourcePath")?,
                field(original, "RelativePath")?,
            ),
        });
    }
    Ok(accounts)
}

fn lookup(forms: &Forms, accounts: &Accounts, request: &Value) -> Result<Value> {
    let account = field(request, "account")?;
    let query = forms.spellings(field(request, "source")?, field(request, "relative")?);
    let records = accounts.get(account).map_or(&[][..], Vec::as_slice);
    // A partial understanding of an account cannot establish a missing identity.
    if records.iter().any(|record| !record.explained()) {
        return Ok(json!({"status": "unqualified-history"}));
    }
    let mut keys = BTreeSet::new();
    for record in records {
        // Match both parts under one profile. Mixing source/relative decisions can invent a row.
        if record
            .spellings
            .iter()
            .zip(&query)
            .any(|(display, requested)| display == requested)
        {
            keys.insert(&record.stored);
        }
    }
    let Some(key) = keys.pop_first() else {
        let concordant = query.iter().all(|form| form == &query[0]);
        return Ok(
            json!({"status": if concordant { "absent-concordant" } else { "absent-profile-dependent" }}),
        );
    };
    if !keys.is_empty() {
        return Ok(json!({"status": "ambiguous", "distinctStoredKeys": keys.len() + 1}));
    }

    let mut tables = BTreeSet::new();
    for record in records.iter().filter(|record| &record.stored == key) {
        if !record.accepts_in_every_possible_origin(&query) {
            return Ok(json!({"status": "possible-alias"}));
        }
        tables.insert(record.table);
    }
    Ok(json!({"status": "existing", "storedKey": key, "tables": tables}))
}

fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn limited(reader: impl Read, limit: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader.take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        return Err("synthetic input exceeds the fixture limit".into());
    }
    Ok(bytes)
}

fn verify_backup(filename: &str, expected: &str) -> Result<()> {
    for suffix in ["-journal", "-wal", "-shm"] {
        match fs::symlink_metadata(format!("{filename}{suffix}")) {
            Err(error) if error.kind() == ErrorKind::NotFound => {}
            Ok(_) => return Err("a standalone backup without SQLite companions is required".into()),
            Err(error) => return Err(error.into()),
        }
    }
    if !fs::symlink_metadata(filename)?.file_type().is_file()
        || digest(&limited(fs::File::open(filename)?, 16 * 1024 * 1024)?) != expected
    {
        return Err("synthetic snapshot digest or file type differs".into());
    }
    Ok(())
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 3 {
        return Err(
            "usage: inspect_stored_keys <synthetic-backup-directory> <mode> <snapshot-sha256>"
                .into(),
        );
    }
    let mode = args[1].to_str().ok_or("invalid comparison mode")?;
    let expected = args[2].to_str().ok_or("invalid digest")?;
    let root = fs::canonicalize("artifacts/rust")?;
    let dir = fs::canonicalize(Path::new(&args[0]))?;
    if !dir.starts_with(&root) || dir == root {
        return Err("expected a private fixture below artifacts/rust".into());
    }
    let marker: Value = serde_json::from_slice(&limited(
        fs::File::open(dir.join("manifest.json"))?,
        1024 * 1024,
    )?)?;
    if !matches!(
        marker["format"].as_str(),
        Some("ifw-qualified-path-key-fixture-v1" | "ifw-derived-path-key-control-v1")
    ) || marker["cases"][mode]["sha256"] != expected
    {
        return Err("synthetic fixture manifest or recorded snapshot digest differs".into());
    }
    let forms = Forms::load(mode)?;
    std::env::set_current_dir(dir)?;
    let filename = format!("{mode}.db");
    verify_backup(&filename, expected)?;
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
    let accounts = read_records(&db, &forms)?;
    let observations: Vec<_> = queries
        .iter()
        .map(|query| lookup(&forms, &accounts, query))
        .collect::<Result<_>>()?;
    // These tables contain no original pair of displayed paths. Their values never grant a lookup.
    let ownership: i64 = db.query_row("SELECT count(*) FROM owned_albums", [], |row| row.get(0))?;
    let history: i64 = db.query_row("SELECT count(*) FROM sync_account_status", [], |row| {
        row.get(0)
    })?;
    drop(db);
    verify_backup(&filename, expected)?;
    let output = json!({
        "format": "ifw-stored-path-key-observations-v1", "inputFormat": marker["format"], "mode": mode, "snapshotSha256": expected,
        "os": std::env::consts::OS, "arch": std::env::consts::ARCH, "lookup": observations,
        "opaqueOwnershipRows": ownership, "transferHistoryRows": history,
    });
    serde_json::to_writer(std::io::stdout().lock(), &output)?;
    Ok(())
}
