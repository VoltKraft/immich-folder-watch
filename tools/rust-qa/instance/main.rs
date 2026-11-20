//! Native, single-use activation and writer-lock probes for marked synthetic profiles.
use std::env;
use std::fs::{self, OpenOptions, TryLockError};
use std::io::{self, Write};
use std::path::Path;
use std::time::Duration;

#[cfg(target_os = "linux")]
#[path = "unix.rs"]
mod platform;
#[cfg(windows)]
#[path = "windows.rs"]
mod platform;

const SIGNAL: &[u8] = b"SHOW_GUI";
const TIMEOUT: Duration = Duration::from_secs(20);

fn announce(event: &str) -> io::Result<()> {
    println!("{event}");
    io::stdout().flush()
}

fn writer(root: &Path) -> io::Result<()> {
    let mut options = OpenOptions::new();
    options.read(true).write(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        // Keep the same pre-created filesystem entry for subsequent writers.
        options.share_mode(3);
    }
    let file = options.open(root.join("writer.lock"))?;
    match file.try_lock() {
        Err(TryLockError::WouldBlock) => return announce("WRITER_BUSY"),
        Err(TryLockError::Error(error)) => return Err(error),
        Ok(()) => {}
    }
    announce("WRITER_HELD")?;
    let mut command = String::new();
    io::stdin().read_line(&mut command)?;
    if command.trim_end() != "RELEASE" {
        return Err(io::Error::other("writer control stream closed"));
    }
    file.unlock()?;
    announce("WRITER_RELEASED")
}

fn main() -> io::Result<()> {
    let args: Vec<_> = env::args_os().collect();
    if args.len() != 5 {
        return Err(io::Error::other(
            "expected role, fixture directory, owner and peer PID",
        ));
    }
    let root = Path::new(&args[2]);
    if !root.is_absolute() || fs::read(root.join(".ifw-instance-fixture"))? != b"synthetic-only\n" {
        return Err(io::Error::other("expected a marked synthetic profile"));
    }
    let owner = args[3].to_str().ok_or(io::ErrorKind::InvalidInput)?;
    let role = args[1].to_str().ok_or(io::ErrorKind::InvalidInput)?;
    platform::check_environment(root, owner)?;
    if role == "writer" {
        return writer(root);
    }
    let peer = args[4]
        .to_str()
        .and_then(|pid| pid.parse::<u32>().ok())
        .filter(|pid| *pid > 0)
        .ok_or(io::ErrorKind::InvalidInput)?;
    match role {
        "listen" => platform::listen(root, owner, peer),
        "signal" => platform::signal(root, owner, peer),
        _ => Err(io::ErrorKind::InvalidInput.into()),
    }
}
