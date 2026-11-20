//! Bounded, read-only uploadNew inventory for the development-only comparison.
#![forbid(unsafe_code)]

use safe_fs::{Directory, EntryKind};
use serde::Deserialize;
use std::collections::HashMap;
use std::error::Error;
use std::io::{self, Read};
use std::net::{Ipv4Addr, SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::time::{Duration, Instant, SystemTime};

const MAX_CONFIG: usize = 65_536;
const MAX_ENTRIES: usize = 110_000;
type Fingerprints = HashMap<PathBuf, (u64, SystemTime)>;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Config {
    immich: Server,
    watch: Watch,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Server {
    server_api_url: String,
    api_key: String,
    allow_insecure_http: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Watch {
    sources: Vec<Source>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Source {
    path: PathBuf,
    sync_mode: String,
    include_subdirectories: bool,
    delete_after_upload: bool,
    extensions: Vec<String>,
}

fn configuration() -> Result<Directory, Box<dyn Error>> {
    if std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
        || std::env::var("IFW_QA_BENCHMARK").as_deref() != Ok("1")
        || std::env::var("DBUS_SESSION_BUS_ADDRESS").as_deref() != Ok("unix:path=/tmp/session-bus")
    {
        return Err("Expected an isolated development comparison".into());
    }
    let home = PathBuf::from(std::env::var_os("XDG_CONFIG_HOME").ok_or("Missing test profile")?);
    if !home.starts_with("/qa") {
        return Err("A synthetic test profile is required".into());
    }
    let mut text = String::new();
    std::fs::File::open(home.join("immich-folder-watch/config.yaml"))?
        .take((MAX_CONFIG + 1) as u64)
        .read_to_string(&mut text)?;
    if text.len() > MAX_CONFIG {
        return Err("Configuration byte budget exceeded".into());
    }
    let options = serde_saphyr::options! {
        budget: serde_saphyr::budget! { max_reader_input_bytes: Some(MAX_CONFIG), max_depth: 16,
            flow_nesting_limit: 16, max_events: 1000, max_nodes: 250, max_documents: 1,
            max_total_scalar_bytes: 32_768, max_aliases: 16, max_anchors: 16, max_inclusion_depth: 0, },
    };
    let config: Config = serde_saphyr::from_str_with_options(&text, options)
        .map_err(|_| "Invalid synthetic performance configuration")?;
    let [source] = config.watch.sources.as_slice() else {
        return Err("Expected one comparison source".into());
    };
    if config.immich.server_api_url != "http://127.0.0.1:9/api"
        || config.immich.api_key != "synthetic-benchmark"
        || !config.immich.allow_insecure_http
        || !matches!(source.path.to_str(), Some("/qa/files" | "/qa/empty"))
        || source.sync_mode != "uploadNew"
        || !source.include_subdirectories
        || source.delete_after_upload
        || source.extensions != [".jpg"]
    {
        return Err("Expected the offline recursive uploadNew JPEG workload".into());
    }
    Ok(Directory::open_root(&source.path)?)
}

fn inventory(
    directory: &Directory,
    relative: &Path,
    depth: usize,
    remaining: &mut usize,
    result: &mut Fingerprints,
    stopped: &AtomicBool,
) -> io::Result<()> {
    if depth > 16 {
        return Err(io::Error::other("Directory nesting limit exceeded"));
    }
    let entries = directory.entries((*remaining).min(4096))?;
    *remaining -= entries.len();
    for entry in entries {
        if stopped.load(Ordering::Relaxed) {
            return Err(io::Error::new(io::ErrorKind::Interrupted, "Worker stopped"));
        }
        let path = relative.join(&entry.name);
        match entry.kind {
            EntryKind::Directory => {
                let child = directory.open_directory(&entry.name)?;
                inventory(&child, &path, depth + 1, remaining, result, stopped)?;
            }
            EntryKind::File
                if path
                    .extension()
                    .is_some_and(|e| e.eq_ignore_ascii_case("jpg")) =>
            {
                let file = directory.open_file(&entry.name)?;
                let meta = file.metadata()?;
                result.insert(path, (meta.len(), meta.modified()?));
            }
            _ => {}
        }
    }
    Ok(())
}

fn offline_probe() -> io::Result<()> {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, 9));
    match TcpStream::connect_timeout(&address, Duration::from_millis(500)) {
        Err(error) if error.kind() == io::ErrorKind::ConnectionRefused => Ok(()),
        Ok(_) => Err(io::Error::other(
            "Expected the closed private offline endpoint",
        )),
        Err(error) => Err(error),
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = configuration()?;
    let stopped = Arc::new(AtomicBool::new(false));
    let (sender, shutdown) = mpsc::sync_channel(1);
    let cancellation = Arc::clone(&stopped);
    std::thread::spawn(move || {
        // The supervisor owns the only write end and closes it on shutdown.
        let mut byte = [0];
        let _ = io::stdin().read(&mut byte);
        cancellation.store(true, Ordering::Relaxed);
        let _ = sender.send(());
    });
    offline_probe()?;
    let mut last_ping = Instant::now();
    let mut previous = Fingerprints::new();
    let mut sweep = 0_u64;
    println!("INVENTORY_STARTED");
    loop {
        let mut snapshot = Fingerprints::new();
        let mut remaining = MAX_ENTRIES;
        match inventory(
            &root,
            Path::new(""),
            0,
            &mut remaining,
            &mut snapshot,
            &stopped,
        ) {
            Err(error) if error.kind() == io::ErrorKind::Interrupted => break,
            Err(error) => return Err(error.into()),
            Ok(()) => {}
        }
        let changed = snapshot
            .iter()
            .filter(|(path, current)| previous.get(*path) != Some(*current))
            .count();
        println!(
            "INVENTORY_COMPLETE files={} changed={} pass={sweep}",
            snapshot.len(),
            changed
        );
        previous = snapshot;
        sweep += 1;
        // Two immediate initial reconciliation passes, then the reference's five-second polling cadence.
        if sweep >= 2 && shutdown.recv_timeout(Duration::from_secs(5)).is_ok() {
            break;
        }
        if last_ping.elapsed() >= Duration::from_secs(30) {
            offline_probe()?;
            last_ping = Instant::now();
        }
    }
    Ok(())
}
