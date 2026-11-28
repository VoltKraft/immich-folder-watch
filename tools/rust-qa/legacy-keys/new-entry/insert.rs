//! Insert three fixed identities on a new private copy of a qualified Linux fixture.
#![forbid(unsafe_code)]

use ifw_legacy::casing::ReferenceCaseMap;
use ifw_legacy::paths::{normalize_absolute_source, normalize_relative_text};
use ifw_sqlite_assessment::{Result, digest, verify_backup};
use rusqlite::{Connection, OpenFlags, params};
use serde_json::{Value, json};
use std::fs::{self, DirBuilder, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::path::Path;

const DONORS: [&str; 2] = [
    "fede848b2b2dee005b1bc788fe20094fccf86b520fbf7e33470a703eae7adfcd",
    "9712893ab6f1fde7c996da611eb2c57720541c8e5847ce89278e5b4a37c53076",
];
const MAPS: [(&str, &str); 2] = [
    (
        "15.1.0",
        "02c4363688e37251e1169559be56231d6e9c398ba046ea3773cdf037df72cd2f",
    ),
    (
        "17.0.0",
        "195bd89b3934dcf9c93b72b4232c53d9787dacb8ebbf2270df7a6a73e53f473e",
    ),
];
const STABLE: &str = "/IfwSynthetic/Insert-ASCII";
const INPUTS: [(&str, &str, &str); 3] = [
    (STABLE, "New/Stable.jpg", "Insert-Asset-A"),
    (STABLE, "New/Only-ƛ.jpg", "Insert-Asset-B"),
    ("/IfwSynthetic/Case-ƛ", "New/Source.jpg", "Insert-Asset-C"),
];
const SQL: &str = "INSERT INTO sync_entries
    (account_scope,source_path,source_key,relative_path,relative_path_key,asset_id,album_name,
     file_size,last_write_time_utc,direction,status,last_synchronized_at_utc,tombstone_expires_at_utc)
    VALUES ('ifw-casing-primary',?1,?2,?3,?4,?5,'Synthetic insert',83,'2024-02-29T03:04:05.1234567+00:00',
            1,0,'2024-02-29T03:04:05.1234567+00:00',NULL)";

// Only the private driver supplies these mounts. Donor paths and their children
// are fixed before either SQLite or this process can open a file by name.
fn require_tmpfs(path: &Path, access: &str) -> Result<()> {
    let encoded = path
        .to_str()
        .ok_or("invalid mount path")?
        .replace('\\', "\\134")
        .replace(' ', "\\040")
        .replace('\t', "\\011")
        .replace('\n', "\\012");
    let mounts = fs::read_to_string("/proc/self/mountinfo")?;
    if mounts.lines().any(|line| {
        let Some((left, right)) = line.split_once(" - ") else {
            return false;
        };
        let fields: Vec<_> = left.split_whitespace().collect();
        fields.get(4) == Some(&encoded.as_str())
            && fields.get(5).and_then(|v| v.split(',').next()) == Some(access)
            && right.starts_with("tmpfs ")
    }) {
        Ok(())
    } else {
        Err("required private study mount is missing".into())
    }
}

fn input(path: &Path) -> Result<Vec<u8>> {
    // Linux O_NOFOLLOW and O_NONBLOCK prevent link traversal and blocking on a FIFO.
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(0o400000 | 0o4000)
        .open(path)?;
    let meta = file.metadata()?;
    if !meta.is_file() || meta.len() == 0 || meta.len() > 1024 * 1024 {
        return Err("expected a bounded regular study file".into());
    }
    let mut bytes = Vec::new();
    file.take(meta.len() + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 != meta.len() {
        return Err("study file size changed".into());
    }
    Ok(bytes)
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [donor, mode, profile, destination] = args.as_slice() else {
        return Err("expected donor, mode, explicit insertion profile and fresh directory".into());
    };
    let area = std::env::current_dir()?.join("artifacts/rust");
    let corpus = area.join("donors");
    let work = area.join("work");
    require_tmpfs(&corpus, "ro")?;
    require_tmpfs(&work, "rw")?;
    let donor = Path::new(donor);
    let destination = Path::new(destination);
    let parent = work.join("cases");
    if !["writer-older", "writer-current"]
        .iter()
        .any(|name| donor == corpus.join(name))
        || destination.parent() != Some(parent.as_path())
        || input(&work.join("new-entry-study.marker"))? != b"ifw-rw02-new-entry-study-v1\n"
        || !matches!(mode.as_str(), "sensitive" | "insensitive")
    {
        return Err("expected a private, explicitly identified synthetic case".into());
    }
    let raw = input(&donor.join("manifest.json"))?;
    let donor_digest = digest(&raw);
    let donor_index = DONORS
        .iter()
        .position(|v| *v == donor_digest)
        .ok_or("unqualified donor manifest")?;
    let manifest: Value = serde_json::from_slice(&raw)?;
    let donor_table = input(&donor.join("invariant-uppercase.tsv"))?;
    if digest(&donor_table) != MAPS[donor_index].1
        || manifest["casingProfile"]["tableSha256"] != MAPS[donor_index].1
    {
        return Err("donor casing table differs".into());
    }
    let (_, expected_map) = MAPS
        .iter()
        .find(|(name, _)| name == profile)
        .ok_or("unqualified insertion profile")?;
    let table: &[u8] = match profile.as_str() {
        "15.1.0" => include_bytes!("../../legacy/casing/unicode-15.1.0.tsv"),
        "17.0.0" => include_bytes!("../../legacy/casing/unicode-17.0.0.tsv"),
        _ => return Err("unqualified insertion profile".into()),
    };
    if digest(table) != *expected_map {
        return Err("insertion table differs".into());
    }
    let map = ReferenceCaseMap::from_reference_tsv(std::str::from_utf8(table)?)?;
    let key = |value: &str| {
        if mode == "sensitive" {
            value.to_owned()
        } else {
            map.uppercase(value)
        }
    };
    let original = donor.join(format!("{mode}.db"));
    let expected = manifest["cases"][mode]["sha256"]
        .as_str()
        .ok_or("missing donor hash")?;
    verify_backup(&original, expected)?;
    let bytes = input(&original)?;
    if digest(&bytes) != expected || bytes.get(18..20) != Some(&[1, 1]) {
        return Err("expected the finalized rollback-journal donor bytes".into());
    }
    let directory = parent.join(destination.file_name().ok_or("missing destination")?);
    DirBuilder::new().mode(0o700).create(&directory)?;
    let file = directory.join("inserted.db");
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&file)?
        .write_all(&bytes)?;
    let mut db = Connection::open_with_flags(&file, OpenFlags::SQLITE_OPEN_READ_WRITE)?;
    let sqlite: String = db.query_row("SELECT sqlite_source_id()", [], |r| r.get(0))?;
    let inputs: Value = serde_json::from_slice(include_bytes!("../../storage/inputs.json"))?;
    if inputs["sqlite"]["source_id"] != sqlite
        || db.pragma_query_value(None, "user_version", |r| r.get::<_, i64>(0))? != 1
    {
        return Err("unexpected pinned SQLite or donor schema".into());
    }
    let tx = db.transaction()?;
    for (source, relative, id) in INPUTS {
        let root = normalize_absolute_source(Path::new(source))?;
        let source_key = key(root.to_str().ok_or("source encoding")?);
        let relative_key = key(&normalize_relative_text(relative)?);
        if tx.execute(SQL, params![source, source_key, relative, relative_key, id])? != 1 {
            return Err("expected one new row".into());
        }
    }
    tx.commit()?;
    drop(db);
    let after = digest(&fs::read(&file)?);
    verify_backup(&file, &after)?;
    verify_backup(&original, expected)?;
    let receipt = json!({"format":"ifw-study-new-entries-v1","donorManifest":donor_digest,
        "before":expected,"after":after,"mode":mode,"chosenProfile":profile,"tableSha256":expected_map,
        "sqliteSourceId":sqlite});
    fs::write(
        directory.join("receipt.json"),
        serde_json::to_vec(&receipt)?,
    )?;
    Ok(())
}
