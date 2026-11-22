use super::{launcher_delivery, win32_instance as local};
use std::ffi::c_void;
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
use std::os::windows::io::{AsRawHandle, OwnedHandle, RawHandle};
use std::path::{Path, PathBuf};
use std::ptr::null_mut;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::TrySendError;
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

const SHOW: &[u8] = b"SHOW_GUI";
const TIMEOUT: Duration = Duration::from_secs(2);

#[link(name = "kernel32")]
unsafe extern "system" {
    fn PeekNamedPipe(
        pipe: RawHandle,
        data: *mut c_void,
        size: u32,
        read: *mut u32,
        available: *mut u32,
        left: *mut u32,
    ) -> i32;
    fn DisconnectNamedPipe(pipe: RawHandle) -> i32;
}

pub enum Launch {
    Disabled,
    Primary(Listener),
    Secondary,
}

pub struct Listener {
    _pins: [File; 3],
    pipe: String,
    stopping: Arc<AtomicBool>,
    worker: Option<JoinHandle<io::Result<()>>>,
    // Drop the election handle last so an immediately relaunched primary can write its PID.
    _owner: OwnedHandle,
}

impl Listener {
    pub fn stop(&mut self) -> io::Result<()> {
        let Some(worker) = self.worker.take() else {
            return Ok(());
        };
        self.stopping.store(true, Ordering::Release);
        worker.thread().unpark();
        let deadline = Instant::now() + TIMEOUT;
        while !worker.is_finished() {
            // Connect to our own waiting listener and close without sending a command.
            // This also covers a listener between its stop check and ConnectNamedPipe.
            drop(local::client(&self.pipe));
            if Instant::now() >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "local launcher did not drain",
                ));
            }
            thread::sleep(Duration::from_millis(10));
        }
        worker
            .join()
            .map_err(|_| io::Error::other("local launcher failed"))?
    }
}

impl Drop for Listener {
    fn drop(&mut self) {
        if let Err(error) = self.stop() {
            eprintln!("Local launcher cleanup failed: {error}");
        }
    }
}

fn pinned(path: &Path, directory: bool, writable: bool) -> io::Result<File> {
    // Hold the directory and original regular files without delete sharing. Only the elected
    // primary may rewrite the pre-created PID file. Check the opened object before writing.
    let file = OpenOptions::new()
        .read(true)
        .write(writable)
        .share_mode(if writable { 1 } else { 3 })
        .custom_flags(0x0220_0000)
        .open(path)?;
    let md = file.metadata()?;
    if md.file_attributes() & 0x440 != 0
        || md.is_dir() != directory
        || (!directory && !md.is_file())
    {
        return Err(io::Error::other("unexpected launcher profile object"));
    }
    Ok(file)
}

fn read_bounded(file: &File, limit: usize) -> io::Result<String> {
    let mut text = String::new();
    file.take((limit + 1) as u64).read_to_string(&mut text)?;
    if text.len() > limit {
        return Err(io::ErrorKind::InvalidData.into());
    }
    Ok(text)
}

fn received(mut pipe: &File, stopping: &AtomicBool) -> io::Result<bool> {
    let deadline = Instant::now() + TIMEOUT;
    let mut bytes = [0; 9];
    let mut filled = 0;
    while !stopping.load(Ordering::Acquire) && Instant::now() < deadline {
        let mut available = 0;
        // The server uniquely owns this live pipe. Peek lets us bound an individual read
        // without polling while the application is idle and no client is connected.
        if unsafe {
            PeekNamedPipe(
                pipe.as_raw_handle(),
                null_mut(),
                0,
                null_mut(),
                &mut available,
                null_mut(),
            )
        } == 0
        {
            let error = io::Error::last_os_error();
            return if matches!(error.raw_os_error(), Some(109 | 232 | 233)) {
                Ok(&bytes[..filled] == SHOW)
            } else {
                Err(error)
            };
        }
        if available == 0 {
            thread::sleep(Duration::from_millis(2));
            continue;
        }
        let take = (available as usize).min(bytes.len() - filled);
        let count = pipe.read(&mut bytes[filled..filled + take])?;
        filled += count;
        if count == 0 {
            return Ok(&bytes[..filled] == SHOW);
        }
        if filled > SHOW.len() {
            return Ok(false);
        }
    }
    Ok(false)
}

fn listen<T>(
    pipe: File,
    stopping: &AtomicBool,
    open: impl Fn() -> Result<(), TrySendError<T>>,
) -> io::Result<()> {
    while !stopping.load(Ordering::Acquire) {
        match local::accept(&pipe) {
            Ok(()) => {
                if stopping.load(Ordering::Acquire) {
                    break;
                }
                let client = local::peer_pid(&pipe, false)?;
                if received(&pipe, stopping)? && launcher_delivery::enqueue(stopping, &open)? {
                    println!("LAUNCHER_OPEN client={client}");
                }
            }
            Err(error) if error.raw_os_error() == Some(232) => (),
            Err(error) => return Err(error),
        }
        // Keep the original first-instance pipe handle through every connection.
        if unsafe { DisconnectNamedPipe(pipe.as_raw_handle()) } == 0 {
            let error = io::Error::last_os_error();
            if error.raw_os_error() != Some(233) {
                return Err(error);
            }
        }
    }
    Ok(())
}

pub fn start_launcher<T>(
    open: impl Fn() -> Result<(), TrySendError<T>> + Send + 'static,
) -> io::Result<Launch> {
    if std::env::var_os("IFW_QA_WINDOWS_LAUNCHER").is_none() {
        return Ok(Launch::Disabled);
    }
    for (key, value) in [
        ("IFW_QA_WINDOWS_LAUNCHER", "1"),
        ("IFW_QA_ISOLATED", "1"),
        ("RUNNER_ENVIRONMENT", "github-hosted"),
        ("RUNNER_OS", "Windows"),
        ("GITHUB_ACTIONS", "true"),
        ("GITHUB_REPOSITORY", "VoltKraft/immich-folder-watch"),
        ("GITHUB_REF", "refs/heads/rewrite/rust"),
    ] {
        if std::env::var(key).as_deref() != Ok(value) {
            return Err(io::Error::other(
                "expected the private native launcher fixture",
            ));
        }
    }
    let token = std::env::var("IFW_QA_INVENTORY_TOKEN").unwrap_or_default();
    let sid = std::env::var("IFW_QA_LAUNCHER_SID").unwrap_or_default();
    let root = PathBuf::from(std::env::var_os("IFW_QA_INVENTORY_ROOT").unwrap_or_default());
    let temp = PathBuf::from(std::env::var_os("RUNNER_TEMP").unwrap_or_default());
    if !local::valid_sid(&sid)
        || token.len() != 32
        || !token.bytes().all(|b| b.is_ascii_hexdigit())
        || !temp.is_absolute()
        || root != temp.join(format!("ifw-rw02-{token}"))
    {
        return Err(io::Error::other("invalid private launcher profile"));
    }
    let dir = pinned(&root, true, false)?;
    let marker = pinned(&root.join("inventory.owner"), false, false)?;
    if read_bounded(&marker, 32)? != token {
        return Err(io::Error::other("launcher ownership marker mismatch"));
    }
    let mutex = format!(r"Local\ImmichFolderWatch-qa-{sid}-{token}");
    let pipe = format!(r"\\.\pipe\ifw-qa-{sid}-{token}");
    let (owner, primary) = local::mutex(&mutex, Some(&sid))?;
    if !primary {
        // The primary publishes and pins its PID before making its first pipe available.
        let connection = local::connect(&pipe, TIMEOUT)?;
        let pid_file = pinned(&root.join("launcher.pid"), false, false)?;
        let expected = read_bounded(&pid_file, 10)?
            .parse::<u32>()
            .map_err(io::Error::other)?;
        local::send(&connection, expected, SHOW)?;
        println!("LAUNCHER_SECONDARY server={expected}");
        return Ok(Launch::Secondary);
    }
    let pid_file = pinned(&root.join("launcher.pid"), false, true)?;
    pid_file.set_len(0)?;
    write!(&pid_file, "{}", std::process::id())?;
    let server = local::inbound(&pipe, &sid)?;
    let stopping = Arc::new(AtomicBool::new(false));
    let shutdown = Arc::clone(&stopping);
    let worker = thread::Builder::new()
        .name("local-activation".into())
        .spawn(move || listen(server, &shutdown, open))?;
    println!("LAUNCHER_PRIMARY pid={}", std::process::id());
    Ok(Launch::Primary(Listener {
        _owner: owner,
        _pins: [dir, marker, pid_file],
        pipe,
        stopping,
        worker: Some(worker),
    }))
}
