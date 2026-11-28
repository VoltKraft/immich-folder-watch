//! Historical lookup shared by the synthetic SQLite assessment executables.
#![forbid(unsafe_code)]

use ifw_legacy::casing::ReferenceCaseMap;
use ifw_legacy::paths::{normalize_absolute_source, normalize_relative_text};
use rusqlite::{Connection, Transaction, params};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fs;
use std::io::{ErrorKind, Read};
use std::path::{Path, PathBuf};

pub type Result<T> = std::result::Result<T, Box<dyn Error>>;
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

struct PathForms {
    display: Key,
    keys: Vec<Key>,
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

    fn spellings(&self, source: &str, relative: &str) -> Result<PathForms> {
        let native = normalize_absolute_source(Path::new(source))?;
        let source = native
            .to_str()
            .ok_or("source cannot be represented losslessly")?;
        let relative = normalize_relative_text(relative)?;
        let display = [source.to_owned(), relative];
        let keys = if self.maps.is_empty() {
            vec![display.clone()]
        } else {
            self.maps
                .iter()
                .map(|map| [map.uppercase(&display[0]), map.uppercase(&display[1])])
                .collect()
        };
        Ok(PathForms { display, keys })
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

pub fn field<'a>(value: &'a Value, name: &str) -> Result<&'a str> {
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
            spellings: forms
                .spellings(row.get_ref(3)?.as_str()?, row.get_ref(4)?.as_str()?)?
                .keys,
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
            spellings: forms
                .spellings(
                    field(original, "SourcePath")?,
                    field(original, "RelativePath")?,
                )?
                .keys,
        });
    }
    Ok(accounts)
}

pub enum PathLookup {
    AbsentConcordant {
        display: [String; 2],
        key: [String; 2],
    },
    Existing {
        key: [String; 2],
        tables: BTreeSet<&'static str>,
    },
    Unresolved(Value),
}

pub enum InsertDecision {
    Inserted,
    Refused(PathLookup),
}

impl PathLookup {
    pub fn observation(&self) -> Value {
        match self {
            Self::AbsentConcordant { .. } => json!({"status": "absent-concordant"}),
            Self::Existing { key, tables } => {
                json!({"status": "existing", "storedKey": key, "tables": tables})
            }
            Self::Unresolved(reason) => reason.clone(),
        }
    }
}

fn lookup(forms: &Forms, accounts: &Accounts, request: &Value) -> Result<PathLookup> {
    let account = field(request, "account")?;
    let PathForms {
        display,
        keys: query,
    } = forms.spellings(field(request, "source")?, field(request, "relative")?)?;
    let records = accounts.get(account).map_or(&[][..], Vec::as_slice);
    // A partial understanding of an account cannot establish a missing identity.
    if records.iter().any(|record| !record.explained()) {
        return Ok(PathLookup::Unresolved(
            json!({"status": "unqualified-history"}),
        ));
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
        if query.iter().all(|form| form == &query[0]) {
            return Ok(PathLookup::AbsentConcordant {
                display,
                key: query[0].clone(),
            });
        }
        return Ok(PathLookup::Unresolved(
            json!({"status": "absent-profile-dependent"}),
        ));
    };
    if !keys.is_empty() {
        return Ok(PathLookup::Unresolved(
            json!({"status": "ambiguous", "distinctStoredKeys": keys.len() + 1}),
        ));
    }

    let mut tables = BTreeSet::new();
    for record in records.iter().filter(|record| &record.stored == key) {
        if !record.accepts_in_every_possible_origin(&query) {
            return Ok(PathLookup::Unresolved(json!({"status": "possible-alias"})));
        }
        tables.insert(record.table);
    }
    Ok(PathLookup::Existing {
        key: key.clone(),
        tables,
    })
}

pub fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub fn limited(reader: impl Read, limit: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader.take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        return Err("synthetic input exceeds the fixture limit".into());
    }
    Ok(bytes)
}

pub fn verify_backup(path: &Path, expected: &str) -> Result<()> {
    for suffix in ["-journal", "-wal", "-shm"] {
        let mut companion = path.as_os_str().to_owned();
        companion.push(suffix);
        match fs::symlink_metadata(companion) {
            Err(error) if error.kind() == ErrorKind::NotFound => {}
            Ok(_) => return Err("a standalone backup without SQLite companions is required".into()),
            Err(error) => return Err(error.into()),
        }
    }
    if !fs::symlink_metadata(path)?.file_type().is_file()
        || digest(&limited(fs::File::open(path)?, 16 * 1024 * 1024)?) != expected
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

pub struct Fixture {
    pub directory: PathBuf,
    pub format: String,
    pub writer: &'static str,
    pub study_receipt: Option<&'static str>,
    forms: Forms,
}

impl Fixture {
    pub fn load(directory: &Path, mode: &str, expected: &str, study: bool) -> Result<Self> {
        let root = fs::canonicalize("artifacts/rust")?;
        let dir = fs::canonicalize(directory)?;
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
                return Err(
                    "the frozen study requires the writer's native Linux x64 target".into(),
                );
            }
        }
        let forms = Forms::load(mode, profiles, study)?;
        verify_backup(&dir.join(format!("{mode}.db")), expected)?;
        Ok(Self {
            directory: dir,
            format: field(&marker, "format")?.to_owned(),
            writer: writer.name,
            study_receipt: study.then_some(writer.study_receipt),
            forms,
        })
    }

    pub fn inspect(&self, db: &Connection, requests: &[Value]) -> Result<Vec<PathLookup>> {
        let accounts = read_records(db, &self.forms)?;
        requests
            .iter()
            .map(|q| lookup(&self.forms, &accounts, q))
            .collect()
    }

    /// Insert one synthetic row using the display and key verified in the caller's write transaction.
    pub fn insert_new(&self, tx: &Transaction<'_>, request: &Value) -> Result<InsertDecision> {
        let answer = lookup(&self.forms, &read_records(tx, &self.forms)?, request)?;
        let PathLookup::AbsentConcordant { display, key } = answer else {
            return Ok(InsertDecision::Refused(answer));
        };
        let count = tx.execute(
            "INSERT INTO sync_entries
             (account_scope,source_path,source_key,relative_path,relative_path_key,asset_id,album_name,
              file_size,last_write_time_utc,direction,status,last_synchronized_at_utc,tombstone_expires_at_utc)
             VALUES (?1,?2,?3,?4,?5,?6,'Synthetic insert',83,'2024-02-29T03:04:05.1234567+00:00',
                     1,0,'2024-02-29T03:04:05.1234567+00:00',NULL)",
            params![field(request, "account")?, display[0], key[0], display[1], key[1], field(request, "asset")?],
        )?;
        if count != 1 {
            return Err("expected exactly one inserted synthetic entry".into());
        }
        Ok(InsertDecision::Inserted)
    }
}
