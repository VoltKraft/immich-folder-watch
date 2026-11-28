//! Admit only the fresh profile prepared by the hosted MSI upload supervisor.

use super::{LIMIT, Profile};
use ifw_sqlite_assessment::{Result, limited};
use std::env;
use std::ffi::OsStr;
use std::fs::{self, File, OpenOptions};
use std::io::ErrorKind;
use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

fn lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

fn pin(path: &Path, directory: bool, allow_write: bool) -> Result<File> {
    // Open the reparse point itself and refuse it. Excluding FILE_SHARE_DELETE
    // preserves the named object while SQLite opens its own connection.
    const OPEN_REPARSE_POINT: u32 = 0x0020_0000;
    const BACKUP_SEMANTICS: u32 = 0x0200_0000;
    let handle = OpenOptions::new()
        .read(true)
        .share_mode(if allow_write { 3 } else { 1 })
        .custom_flags(OPEN_REPARSE_POINT | if directory { BACKUP_SEMANTICS } else { 0 })
        .open(path)?;
    let info = handle.metadata()?;
    if info.file_attributes() & 0x400 != 0
        || (directory && !info.is_dir())
        || (!directory && (!info.is_file() || info.len() > LIMIT))
    {
        return Err("unexpected object in the synthetic Windows profile".into());
    }
    Ok(handle)
}

pub(super) fn profile() -> Result<Profile> {
    let args: Vec<_> = env::args().skip(1).collect();
    let [port, config_hash, marker, work] = args.as_slice() else {
        return Err(
            "expected the peer port, config digest, profile marker and MSI scratch directory"
                .into(),
        );
    };
    let port: u16 = port.parse()?;
    let work = Path::new(work);
    let marker = Path::new(marker);
    let runner_temp = PathBuf::from(env::var_os("RUNNER_TEMP").ok_or("missing runner temp")?);
    let profile = PathBuf::from(env::var_os("LOCALAPPDATA").ok_or("missing local app data")?)
        .join("Immich Folder Watch");
    if env::var("GITHUB_ACTIONS").as_deref() != Ok("true")
        || env::var("GITHUB_REPOSITORY").as_deref() != Ok("VoltKraft/immich-folder-watch")
        || env::var("GITHUB_REF").as_deref() != Ok("refs/heads/rewrite/rust")
        || port == 0
        || !lower_hex(config_hash, 64)
        || !work.is_absolute()
        || !profile.is_absolute()
        || !work
            .file_name()
            .and_then(OsStr::to_str)
            .is_some_and(|n| n.starts_with("ifw-msi-"))
        || work
            .parent()
            .ok_or("missing scratch parent")?
            .canonicalize()?
            != runner_temp.canonicalize()?
        || work.canonicalize()? != env::current_dir()?.canonicalize()?
        || marker
            .parent()
            .ok_or("missing profile marker parent")?
            .canonicalize()?
            != profile.canonicalize()?
    {
        return Err("expected the disposable native rewrite runner and marked MSI profile".into());
    }
    let token = marker
        .file_name()
        .and_then(OsStr::to_str)
        .and_then(|n| n.strip_prefix(".rw02-owned-"))
        .filter(|s| lower_hex(s, 32))
        .ok_or("invalid synthetic profile marker")?;
    let media = work.join("wpf-media");
    let mut pins = vec![
        pin(work, true, true)?,
        pin(&media, true, true)?,
        pin(&profile, true, true)?,
    ];
    let marker = pin(marker, false, false)?;
    if limited(&marker, 32)? != token.as_bytes() {
        return Err("the Windows synthetic profile marker changed".into());
    }
    pins.push(marker);
    pins.push(pin(&profile.join("config.yaml"), false, false)?);
    pins.push(pin(&profile.join("sync-state.db"), false, true)?);
    for suffix in ["wal", "shm"] {
        let companion = profile.join(format!("sync-state.db-{suffix}"));
        match fs::symlink_metadata(&companion) {
            Ok(_) => pins.push(pin(&companion, false, true)?),
            Err(e) if e.kind() == ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
        }
    }
    for name in [
        "installed-returned.db",
        "installed-returned.db-wal",
        "installed-returned.db-shm",
        "installed-returned.db-journal",
    ] {
        match fs::symlink_metadata(work.join(name)) {
            Err(e) if e.kind() == ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
            Ok(_) => return Err("expected a fresh backup destination".into()),
        }
    }
    Ok(Profile {
        port,
        directory: profile,
        media,
        returned: work.join("installed-returned.db"),
        config_hash: config_hash.clone(),
        _pins: pins,
    })
}
