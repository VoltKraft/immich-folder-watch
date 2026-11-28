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
use windows::Win32::Foundation::{FILETIME, HANDLE, WAIT_TIMEOUT};
use windows::Win32::System::Threading::{
    GetCurrentProcess, GetProcessTimes, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
    PROCESS_SYNCHRONIZE, WaitForSingleObject,
};
use windows::Win32::UI::WindowsAndMessaging::AllowSetForegroundWindow;
use windows::core::Owned;

const SHOW: &[u8] = b"SHOW_GUI";
const TIMEOUT: Duration = Duration::from_secs(2);

#[link(name = "user32")]
unsafe extern "system" {
    fn GetThreadDesktop(tid: u32) -> RawHandle;
    fn GetUserObjectInformationW(
        object: RawHandle,
        index: i32,
        value: *mut c_void,
        bytes: u32,
        used: *mut u32,
    ) -> i32;
}

fn on_input_desktop() -> bool {
    const UOI_IO: i32 = 6;
    let mut active = 0i32;
    let mut used = 0;
    // The current thread lends its desktop. UOI_IO reports whether it accepts user input.
    unsafe {
        let desktop = GetThreadDesktop(super::GetCurrentThreadId());
        !desktop.is_null()
            && GetUserObjectInformationW(
                desktop,
                UOI_IO,
                (&raw mut active).cast(),
                size_of_val(&active) as u32,
                &mut used,
            ) != 0
            && active != 0
    }
}

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

fn creation_time(process: HANDLE) -> Option<u64> {
    let mut times = [FILETIME::default(); 4];
    let [created, exit, kernel, user] = &mut times;
    // Both callers retain the process handle throughout this query.
    unsafe { GetProcessTimes(process, created, exit, kernel, user) }.ok()?;
    Some((u64::from(created.dwHighDateTime) << 32) | u64::from(created.dwLowDateTime))
}

fn offer_foreground(connection: &File, expected: u32, created: Option<u64>) -> io::Result<String> {
    if local::peer_pid(connection, true)? != expected {
        return Err(io::Error::other("unexpected local activation peer"));
    }
    let Some(created) = created else {
        return Ok("unavailable reason=legacy-pid".into());
    };
    if !on_input_desktop() {
        return Ok("unavailable reason=input-desktop".into());
    }
    unsafe {
        let access = PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SYNCHRONIZE;
        let Ok(process) = OpenProcess(access, false, expected) else {
            return Ok("unavailable reason=process-handle".into());
        };
        let process = Owned::new(process);
        // Bind the live process object to the elected primary before offering only
        // that PID the caller's existing foreground permission. Windows may decline.
        if creation_time(*process) != Some(created)
            || WaitForSingleObject(*process, 0) != WAIT_TIMEOUT
        {
            return Ok("unavailable reason=process-identity".into());
        }
        Ok(match AllowSetForegroundWindow(expected) {
            Ok(()) => "granted".into(),
            Err(error) => format!("denied hresult={}", error.code().0),
        })
    }
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
    let (temp, local_vm) = crate::fixture_temp()
        .ok_or_else(|| io::Error::other("expected the private native launcher fixture"))?;
    if std::env::var("IFW_QA_WINDOWS_LAUNCHER").as_deref() != Ok("1")
        || std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
        || (!local_vm
            && (std::env::var("GITHUB_REPOSITORY").as_deref()
                != Ok("VoltKraft/immich-folder-watch")
                || std::env::var("GITHUB_REF").as_deref() != Ok("refs/heads/rewrite/rust")))
    {
        return Err(io::Error::other(
            "expected the private native launcher fixture",
        ));
    }
    let token = std::env::var("IFW_QA_INVENTORY_TOKEN").unwrap_or_default();
    let sid = std::env::var("IFW_QA_LAUNCHER_SID").unwrap_or_default();
    let root = PathBuf::from(std::env::var_os("IFW_QA_INVENTORY_ROOT").unwrap_or_default());
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
        let (expected, created) =
            launcher_delivery::primary_identity(&read_bounded(&pid_file, 31)?)?;
        let grant = if std::env::args_os().len() == 1 {
            Some(offer_foreground(&connection, expected, created)?)
        } else {
            None
        };
        local::send(&connection, expected, SHOW)?;
        if let Some(state) = grant {
            println!("LAUNCHER_FOREGROUND_GRANT server={expected} state={state}");
        }
        println!("LAUNCHER_SECONDARY server={expected}");
        return Ok(Launch::Secondary);
    }
    let pid_file = pinned(&root.join("launcher.pid"), false, true)?;
    pid_file.set_len(0)?;
    write!(&pid_file, "{}", std::process::id())?;
    if let Some(created) = creation_time(unsafe { GetCurrentProcess() }) {
        write!(&pid_file, " {created}")?;
    }
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
