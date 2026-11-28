//! Copy one committed upload from the installed reference application's live synthetic profile.
#![forbid(unsafe_code)]

use ifw_sqlite_assessment::{Result, digest, limited, verify_backup};
use rusqlite::backup::Backup;
use rusqlite::{Connection, OpenFlags, params};
use serde_json::json;
use std::fs::{self, File};
#[cfg(target_os = "linux")]
use std::path::Path;
use std::path::PathBuf;
use std::time::Duration;

#[cfg(target_os = "linux")]
const PROFILE: &str = "/tmp/home/.var/app/io.github.voltkraft.immich-folder-watch";
const LIMIT: u64 = 16 * 1024 * 1024;

struct Profile {
    port: u16,
    directory: PathBuf,
    media: PathBuf,
    returned: PathBuf,
    config_hash: String,
    #[cfg(windows)]
    _pins: Vec<File>,
}

#[cfg(windows)]
#[path = "installed_upload_backup/windows.rs"]
mod windows;

#[cfg(target_os = "linux")]
fn profile() -> Result<Profile> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [port, config_hash] = args.as_slice() else {
        return Err(
            "usage: installed_upload_backup <private-loopback-port> <config-sha256>".into(),
        );
    };
    let port: u16 = port.parse()?;
    if port == 0
        || !cfg!(any(target_arch = "x86_64", target_arch = "aarch64"))
        || std::env::current_dir()? != Path::new("/qa")
        || std::env::var("HOME")? != "/tmp/home"
        || fs::read_to_string("/proc/net/route")?.lines().count() != 1
    {
        return Err(
            "the installed upload requires the private offline Linux x64 or ARM64 desktop".into(),
        );
    }
    let directory = Path::new(PROFILE).join("config/immich-folder-watch");
    for name in ["sync-state.db", "config.yaml"] {
        let path = directory.join(name);
        if path.canonicalize()? != path {
            return Err("unexpected live synthetic upload profile".into());
        }
    }
    Ok(Profile {
        port,
        directory,
        media: Path::new(PROFILE).join("data/interop-upload"),
        returned: Path::new("/qa/installed-returned.db").to_owned(),
        config_hash: config_hash.clone(),
    })
}

#[cfg(windows)]
use windows::profile;

fn run() -> Result<()> {
    let profile = profile()?;
    let path = profile.directory.join("sync-state.db");
    let config = profile.directory.join("config.yaml");
    if !fs::symlink_metadata(&path)?.is_file()
        || path.metadata()?.len() > LIMIT
        || digest(&limited(File::open(config)?, 4096)?) != profile.config_hash
    {
        return Err("unexpected live synthetic upload profile".into());
    }
    let source = Connection::open_with_flags(
        &path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )?;
    source.execute_batch("PRAGMA trusted_schema=OFF; PRAGMA query_only=ON; BEGIN")?;
    let port = profile.port;
    let scope =
        digest(format!("http://127.0.0.1:{port}/api\nsynthetic-installed-upload").as_bytes());
    let read_i64 = |sql| source.query_one::<i64, _, _>(sql, [], |row| row.get(0));
    if read_i64("PRAGMA user_version")? != 1
        || read_i64("PRAGMA page_count")? * read_i64("PRAGMA page_size")? > LIMIT as i64
        || read_i64("SELECT count(*) FROM sync_entries")? != 1
        || source.query_one::<i64, _, _>(
            "SELECT count(*) FROM sync_entries e JOIN sync_account_status a USING(account_scope)
             WHERE e.account_scope=?1 AND source_path=?2 AND relative_path='signed-worker.png'
             AND asset_id='85a783ae-f459-41e9-ad2a-9f1fdc123742' AND file_size=69
             AND direction=0 AND status=0 AND a.last_successful_sync_utc IS NOT NULL",
            params![
                scope,
                profile
                    .media
                    .to_str()
                    .ok_or("invalid synthetic source path")?
            ],
            |row| row.get(0),
        )? != 1
    {
        return Err("expected the signed worker's committed upload and account history".into());
    }
    let returned = profile.returned.as_path();
    File::create_new(returned)?;
    let mut output = Connection::open_with_flags(
        returned,
        OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )?;
    Backup::new(&source, &mut output)?.run_to_completion(16, Duration::from_millis(1), None)?;
    if output.query_one::<String, _, _>("PRAGMA journal_mode=DELETE", [], |r| r.get(0))? != "delete"
        || output.query_one::<String, _, _>("PRAGMA integrity_check", [], |r| r.get(0))? != "ok"
    {
        return Err("cannot finalize the installed worker backup".into());
    }
    output.close().map_err(|(_, error)| error)?;
    let hash = digest(&limited(File::open(returned)?, LIMIT)?);
    verify_backup(returned, &hash)?;
    let source_id =
        source.query_one::<String, _, _>("SELECT sqlite_source_id()", [], |r| r.get(0))?;
    println!(
        "{}",
        json!({"returnedSha256": hash, "accountScope":scope, "sqliteSourceId":source_id})
    );
    Ok(())
}

fn main() -> Result<()> {
    run()
}
