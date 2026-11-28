//! Opening a WAL database even read-only can create or update its shared index.
//! Inspect an owned, quiescent migration input in a new private scratch directory.
use super::{Result, UnsupportedSchema, sidecar};
use rusqlite::{Connection, OpenFlags};
use std::fs::{self, File};
use std::io::{self, ErrorKind, Read};
use std::path::Path;

fn copy_input(from: &Path, to: &Path, optional: bool) -> Result<()> {
    let metadata = match fs::symlink_metadata(from) {
        Err(error) if optional && error.kind() == ErrorKind::NotFound => return Ok(()),
        result => result?,
    };
    if !metadata.is_file() {
        return Err("expected a regular migration input".into());
    }
    let mut input = File::open(from)?;
    let mut output = File::create_new(to)?;
    io::copy(&mut input, &mut output)?;
    Ok(())
}

fn require_v1(database: &Connection) -> Result<()> {
    database.pragma_update(None, "trusted_schema", false)?;
    let version: i64 = database.pragma_query_value(None, "user_version", |row| row.get(0))?;
    if version != 1 {
        return Err(UnsupportedSchema(version).into());
    }
    Ok(())
}

// SQLite finalizes a single-database rollback journal by deletion, truncation
// or zeroing its header (see zeroJournalHdr in the pinned SQLite source).
fn require_finalized_journal(path: &Path) -> Result<()> {
    let metadata = match fs::symlink_metadata(path) {
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(()),
        result => result?,
    };
    if !metadata.is_file() {
        return Err("expected a regular rollback journal".into());
    }
    if metadata.len() == 0 {
        return Ok(());
    }
    let mut header = [0; 28];
    let saved = usize::try_from(metadata.len().min(28))?;
    File::open(path)?.read_exact(&mut header[..saved])?;
    if header != [0; 28] {
        return Err("rollback journal requires recovery before WAL preflight".into());
    }
    Ok(())
}

/// The caller owns the profile and keeps all other workers stopped throughout
/// inspection and handoff. SQLite reconstructs its WAL index in scratch.
/// A pending rollback journal requires separate recovery before this handoff.
pub(super) fn open_existing(database: &Path, scratch: &Path) -> Result<Connection> {
    let builder = &mut fs::DirBuilder::new();
    #[cfg(unix)]
    std::os::unix::fs::DirBuilderExt::mode(builder, 0o700);
    builder.create(scratch)?;
    let staged = scratch.join("state.db");
    let flags = OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NO_MUTEX;
    let inspected = (|| -> Result<()> {
        require_finalized_journal(&sidecar(database, "-journal"))?;
        copy_input(database, &staged, false)?;
        copy_input(&sidecar(database, "-wal"), &sidecar(&staged, "-wal"), true)?;
        let copy = Connection::open_with_flags(&staged, flags)?;
        require_v1(&copy)
    })();
    fs::remove_dir_all(scratch)?;
    inspected?;

    let connection = Connection::open_with_flags(database, flags)?;
    if connection.is_readonly("main")? {
        return Err(io::Error::new(
            ErrorKind::PermissionDenied,
            "SQLite opened the original read-only",
        )
        .into());
    }
    require_v1(&connection)?;
    let mode: String = connection.query_one("PRAGMA journal_mode=WAL", [], |r| r.get(0))?;
    if mode != "wal" {
        return Err("existing database did not enter WAL mode".into());
    }
    connection.pragma_update(None, "wal_autocheckpoint", 0)?;
    Ok(connection)
}
