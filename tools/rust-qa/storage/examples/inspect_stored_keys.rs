//! Read previously stored identities in a finalized, synthetic C# SQLite backup.
#![forbid(unsafe_code)]

use ifw_legacy::casing::ReferenceCaseMap;
use ifw_legacy::paths::{normalize_absolute_source, normalize_relative_text};
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
struct Profile {
    name: &'static str,
    table: &'static str,
    sha256: &'static str,
    changed: u64,
    // Original StoreIdentities writer result, independently rechecked by all three C# readers.
    study_receipt: &'static str,
}

const ICU15: Profile = Profile {
    name: "15.1.0",
    table: "tools/rust-qa/legacy/casing/unicode-15.1.0.tsv",
    sha256: "02c4363688e37251e1169559be56231d6e9c398ba046ea3773cdf037df72cd2f",
    changed: 1449,
    study_receipt: "ef4b3573995b1f6cd13bc519895e73b156acc4093e3c401f8742e8c9e2fc5ce0",
};
const ICU17: Profile = Profile {
    name: "17.0.0",
    table: "tools/rust-qa/legacy/casing/unicode-17.0.0.tsv",
    sha256: "195bd89b3934dcf9c93b72b4232c53d9787dacb8ebbf2270df7a6a73e53f473e",
    changed: 1504,
    study_receipt: "4ef03394e3c4466ba129110d6d9fcee4d2b2f7ca2795bd5f59fbbabe0b271105",
};
const MANAGED16: Profile = Profile {
    name: "managed-invariant-10.0.12",
    table: "tools/rust-qa/legacy-invariant/managed-invariant-10.0.12.tsv",
    sha256: "51e3c6f44c782e8e99c355b504f32900da56c9e4a500da83a15a2f807b95b6e4",
    changed: 1475,
    study_receipt: "0fb938ec806cfca482a6c8bab23becba769b0680b2570c3fcf11e0f3dd08a881",
};
const QUALIFIED: &[Profile] = &[ICU15, ICU17];
const STUDY: &[Profile] = &[ICU15, MANAGED16, ICU17];
const STUDY_FORMAT: &str = "ifw-managed-invariant-store-differential-v1";

struct Forms {
    maps: Vec<ReferenceCaseMap>,
}

impl Forms {
    fn load(mode: &str, profiles: &[Profile], study: bool) -> Result<Self> {
        if !matches!(mode, "sensitive" | "insensitive") {
            return Err("an explicit path comparison mode is required".into());
        }
        let mut maps = Vec::new();
        if mode == "insensitive" || study {
            for profile in profiles {
                let data = fs::read(profile.table)?;
                if digest(&data) != profile.sha256 {
                    return Err("unqualified casing input".into());
                }
                if mode == "insensitive" {
                    maps.push(ReferenceCaseMap::from_reference_tsv(std::str::from_utf8(
                        &data,
                    )?)?);
                }
            }
        }
        Ok(Self { maps })
    }

    fn spellings(&self, source: &str, relative: &str) -> Result<Vec<Key>> {
        let native = normalize_absolute_source(Path::new(source))?;
        let source = native
            .to_str()
            .ok_or("source cannot be represented losslessly")?;
        let relative = normalize_relative_text(relative)?;
        if self.maps.is_empty() {
            return Ok(vec![[source.to_owned(), relative]]);
        }
        Ok(self
            .maps
            .iter()
            .map(|map| [map.uppercase(source), map.uppercase(&relative)])
            .collect())
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
        .filter(|text| !text.trim().is_empty())
        .ok_or_else(|| "expected a nonblank identity field".into())
}

fn read_records(db: &Connection, forms: &Forms) -> Result<Accounts> {
    let mut accounts = Accounts::new();
    let mut entries = db.prepare("SELECT account_scope,source_key,relative_path_key,source_path,relative_path FROM sync_entries")?;
    let mut cursor = entries.query([])?;
    while let Some(row) = cursor.next()? {
        accounts.entry(row.get(0)?).or_default().push(Record {
            table: "sync_entries",
            stored: [row.get(1)?, row.get(2)?],
            spellings: forms.spellings(row.get_ref(3)?.as_str()?, row.get_ref(4)?.as_str()?)?,
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
            )?,
        });
    }
    Ok(accounts)
}

fn lookup(forms: &Forms, accounts: &Accounts, request: &Value) -> Result<Value> {
    let account = field(request, "account")?;
    let query = forms.spellings(field(request, "source")?, field(request, "relative")?)?;
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

fn writer_profile<'a>(dir: &Path, marker: &Value, profiles: &'a [Profile]) -> Result<&'a Profile> {
    let path = dir.join("invariant-uppercase.tsv");
    if !fs::symlink_metadata(&path)?.file_type().is_file() {
        return Err("expected the writer's regular casing table".into());
    }
    let checksum = digest(&limited(fs::File::open(path)?, 200_000)?);
    let writer = profiles
        .iter()
        .find(|candidate| candidate.sha256 == checksum)
        .ok_or("unqualified full casing table from the SQLite writer")?;
    let profile = &marker["casingProfile"];
    if profile["tableSha256"] != checksum
        || profile["scannedScalars"] != 1_112_064u64
        || profile["changedScalars"] != writer.changed
        || profile["contextBatchChecked"] != true
    {
        return Err("incomplete same-process writer casing evidence".into());
    }
    Ok(writer)
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let (directory, mode, expected, study) = match args.as_slice() {
        [directory, mode, expected] => (directory, mode, expected, false),
        [flag, directory, mode, expected] if flag == "--three-profile-study" => (directory, mode, expected, true),
        _ => return Err("usage: inspect_stored_keys [--three-profile-study] <synthetic-backup-directory> <mode> <snapshot-sha256>".into()),
    };
    let mode = mode.to_str().ok_or("invalid comparison mode")?;
    let expected = expected.to_str().ok_or("invalid digest")?;
    let root = fs::canonicalize("artifacts/rust")?;
    let dir = fs::canonicalize(Path::new(directory))?;
    if !dir.starts_with(&root) || dir == root {
        return Err("expected a private fixture below artifacts/rust".into());
    }
    let marker_path = dir.join(if study {
        "result.json"
    } else {
        "manifest.json"
    });
    if !fs::symlink_metadata(&marker_path)?.file_type().is_file() {
        return Err("expected a regular fixture manifest".into());
    }
    let bytes = limited(fs::File::open(marker_path)?, 1024 * 1024)?;
    let marker: Value = serde_json::from_slice(&bytes)?;
    let recognized = if study {
        marker["format"] == STUDY_FORMAT
    } else {
        matches!(
            marker["format"].as_str(),
            Some("ifw-qualified-path-key-fixture-v1" | "ifw-derived-path-key-control-v1")
        )
    };
    if !recognized || marker["cases"][mode]["sha256"] != expected {
        return Err("synthetic fixture manifest or recorded snapshot digest differs".into());
    }
    let profiles = if study { STUDY } else { QUALIFIED };
    let writer = writer_profile(&dir, &marker, profiles)?;
    if study {
        // This selection is bound to the three original Fedora x64 writer builds and snapshots.
        if digest(&bytes) != writer.study_receipt {
            return Err("unrecognized frozen study writer receipt".into());
        }
        if marker["os"] != std::env::consts::OS || !cfg!(target_arch = "x86_64") {
            return Err("the frozen study requires the writer's native Linux x64 target".into());
        }
    }
    let forms = Forms::load(mode, profiles, study)?;
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
    let mut output = json!({
        "format": "ifw-stored-path-key-observations-v1", "inputFormat": marker["format"], "mode": mode, "snapshotSha256": expected,
        "writerProfile": writer.name,
        "os": std::env::consts::OS, "arch": std::env::consts::ARCH, "lookup": observations,
        "opaqueOwnershipRows": ownership, "transferHistoryRows": history,
    });
    if study {
        output["writerReceiptSha256"] = json!(writer.study_receipt);
    }
    serde_json::to_writer(std::io::stdout().lock(), &output)?;
    Ok(())
}
