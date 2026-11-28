//! Own the optional Windows inventory process on a disposable benchmark VM.
use std::fs::File;
#[cfg(windows)]
use std::fs::OpenOptions;
use std::io::{self, Read, Write};
#[cfg(windows)]
use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, SyncSender, TrySendError};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

pub(super) struct Benchmark {
    child: Option<Child>,
    program: Option<Command>,
    _pins: Vec<File>,
}

#[cfg(windows)]
fn pin(path: &Path, directory: bool) -> io::Result<File> {
    let file = OpenOptions::new()
        .read(true)
        .share_mode(if directory { 3 } else { 1 })
        .custom_flags(0x0220_0000) // BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        .open(path)?;
    let metadata = file.metadata()?;
    if metadata.file_attributes() & 0x440 != 0
        || (directory && !metadata.is_dir())
        || (!directory && !metadata.is_file())
    {
        return Err(io::Error::other("Unexpected staged inventory object"));
    }
    Ok(file)
}

fn wait_child(
    child: &mut Child,
    timeout: Duration,
) -> io::Result<Option<std::process::ExitStatus>> {
    let deadline = Instant::now() + timeout;
    loop {
        if let Some(status) = child.try_wait()? {
            return Ok(Some(status));
        }
        if Instant::now() >= deadline {
            return Ok(None);
        }
        std::thread::sleep(Duration::from_millis(20));
    }
}

impl Benchmark {
    #[cfg(windows)]
    pub(super) fn start() -> io::Result<Self> {
        if std::env::var("IFW_QA_BENCHMARK").as_deref() != Ok("1") {
            return Ok(Self {
                child: None,
                program: None,
                _pins: Vec::new(),
            });
        }
        let top = std::env::var_os("IFW_QA_INVENTORY_ROOT").map(PathBuf::from);
        let (runner, _) = native_gui_assessment::fixture_temp()
            .ok_or_else(|| io::Error::other("Expected the staged native Windows comparison"))?;
        let exe = std::env::current_exe()?;
        let token = std::env::var("IFW_QA_INVENTORY_TOKEN").unwrap_or_default();
        let Some(top) = top else {
            return Err(io::Error::other("Missing private comparison root"));
        };
        if std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
            || !top.is_absolute()
            || top.parent() != Some(runner.as_path())
            || !top
                .file_name()
                .is_some_and(|n| n.to_string_lossy().starts_with("ifw-rw02-"))
            || token.len() != 32
            || !token.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err(io::Error::other(
                "Expected the staged native Windows comparison",
            ));
        }
        let root = pin(&top, true)?;
        let stage = top.join("subject");
        let staged = pin(&stage, true)?;
        if exe.parent().map(|p| p.canonicalize()).transpose()? != Some(stage.canonicalize()?) {
            return Err(io::Error::other("Unexpected staged supervisor"));
        }
        let marker = pin(&top.join("inventory.owner"), false)?;
        let mut owner = String::new();
        (&marker).take(33).read_to_string(&mut owner)?;
        if owner != token {
            return Err(io::Error::other(
                "Windows comparison ownership did not match",
            ));
        }
        let worker = stage.join("ifw-performance-worker.exe");
        let image = pin(&worker, false)?;
        let mut program = Command::new(worker);
        program.creation_flags(0x0800_0000); // CREATE_NO_WINDOW for each launch of the pinned worker.
        let mut result = Self {
            child: None,
            program: Some(program),
            _pins: vec![root, staged, marker, image],
        };
        result.spawn_child()?;
        Ok(result)
    }

    fn spawn_child(&mut self) -> io::Result<u32> {
        let program = self
            .program
            .as_mut()
            .ok_or_else(|| io::Error::other("Missing pinned inventory executable"))?;
        if self.child.is_some() {
            return Err(io::Error::other(
                "Previous inventory process is still owned",
            ));
        }
        let child = program.stdin(Stdio::piped()).spawn()?;
        let pid = child.id();
        self.child = Some(child);
        println!("INVENTORY_WORKER pid={pid}");
        Ok(pid)
    }

    /// The existing tray bootstrap byte releases the worker after the observer attaches.
    pub(super) fn release(&mut self) -> io::Result<()> {
        if let Some(pipe) = self.child.as_mut().and_then(|child| child.stdin.as_mut()) {
            pipe.write_all(b"S")?;
        }
        Ok(())
    }

    fn stop_child(&mut self, reason: &str) -> io::Result<Option<Child>> {
        if let Some(child) = self.child.as_mut() {
            let pid = child.id();
            drop(child.stdin.take());
            let status = wait_child(child, Duration::from_secs(6))?.ok_or_else(|| {
                io::Error::new(io::ErrorKind::TimedOut, "Inventory did not exit after EOF")
            })?;
            let reaped = self.child.take();
            println!(
                "WORKER_EXIT pid={pid} reason={reason} success={}",
                status.success()
            );
            // Once the previous process has exited, a user-requested restart
            // can recover a failed worker on that same request.
            if !status.success() && reason != "restart" {
                return Err(io::Error::other("Native comparison inventory failed"));
            }
            return Ok(reaped);
        }
        Ok(None)
    }

    fn restart(&mut self, closing: &AtomicBool) -> io::Result<()> {
        let old = self.stop_child("restart")?;
        if closing.load(Ordering::Acquire) {
            return Ok(());
        }
        let new = self.spawn_child()?;
        self.release()?;
        if let Some(original) = old {
            // Hold the reaped process handle across the spawn so Windows cannot recycle its PID.
            let old = original.id();
            println!("WORKER_RESTARTED old={old} new={new}");
        } else {
            println!("WORKER_STARTED_AFTER_FAILURE new={new}");
        }
        Ok(())
    }
}

#[derive(Clone)]
pub(super) struct Restarts {
    wake: SyncSender<()>,
    closing: Arc<AtomicBool>,
}

impl Restarts {
    pub(super) fn request(&self) {
        if self.closing.load(Ordering::Acquire) {
            return;
        }
        match self.wake.try_send(()) {
            Ok(()) => (),
            Err(TrySendError::Full(_)) => println!("WORKER_RESTART_PENDING"),
            Err(TrySendError::Disconnected(_)) => {
                eprintln!("WORKER_RESTART_FAILED owner disconnected")
            }
        }
    }

    pub(super) fn begin_quit(&self) {
        self.closing.store(true, Ordering::Release);
        // A full restart queue already wakes the owner, even if the UI retains a sender.
        let _ = self.wake.try_send(());
    }
}

pub(super) enum Owner {
    Direct(Box<Benchmark>),
    Tray(Restarts, JoinHandle<io::Result<()>>),
}

impl Owner {
    pub(super) fn new(mut worker: Benchmark, with_tray: bool) -> io::Result<Self> {
        if !with_tray {
            return Ok(Self::Direct(Box::new(worker)));
        }
        let (wake, commands) = mpsc::sync_channel(1);
        let closing = Arc::new(AtomicBool::new(false));
        let stop = Arc::clone(&closing);
        let thread = thread::Builder::new()
            .name("windows-inventory-owner".into())
            .spawn(move || {
                while commands.recv().is_ok() && !stop.load(Ordering::Acquire) {
                    if let Err(error) = worker.restart(&stop) {
                        eprintln!("WORKER_RESTART_FAILED {error}");
                        if stop.load(Ordering::Acquire) {
                            return Err(error);
                        }
                    }
                }
                worker.stop_child("quit")?;
                Ok(())
            })?;
        Ok(Self::Tray(Restarts { wake, closing }, thread))
    }

    pub(super) fn restarts(&self) -> Option<Restarts> {
        match self {
            Self::Tray(requests, _) => Some(requests.clone()),
            Self::Direct(_) => None,
        }
    }

    pub(super) fn finish(self) -> io::Result<()> {
        match self {
            Self::Direct(mut worker) => {
                worker.stop_child("quit")?;
                Ok(())
            }
            Self::Tray(requests, thread) => {
                requests.begin_quit();
                thread
                    .join()
                    .map_err(|_| io::Error::other("Inventory owner panicked"))?
            }
        }
    }
}

impl Drop for Benchmark {
    fn drop(&mut self) {
        if let Some(child) = self.child.as_mut() {
            drop(child.stdin.take());
            if !matches!(wait_child(child, Duration::from_millis(400)), Ok(Some(_))) {
                let _ = child.kill();
                let _ = wait_child(child, Duration::from_secs(2));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{Ipv4Addr, TcpListener, TcpStream};

    #[test]
    #[cfg(windows)]
    fn restart_reaps_original_before_reporting_live_replacement() -> io::Result<()> {
        // The system's native sort reads our synthetic input until the writer closes.
        let system =
            std::env::var_os("SystemRoot").ok_or_else(|| io::Error::other("Missing SystemRoot"))?;
        let sorter = PathBuf::from(system).join("System32/sort.exe");
        let mut child = Command::new(&sorter)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()?;
        let first = child.id();
        let mut original_output = child.stdout.take().unwrap();
        let mut worker = Benchmark {
            child: Some(child),
            program: Some(Command::new(sorter)),
            _pins: Vec::new(),
        };
        worker.release()?;
        worker
            .child
            .as_mut()
            .unwrap()
            .stdin
            .as_mut()
            .unwrap()
            .write_all(b"\r\n")?;
        worker.restart(&AtomicBool::new(false))?;
        let replacement = worker.child.as_mut().unwrap();
        let second = replacement.id();
        assert_ne!(first, second);
        // The original's private stdout reaches EOF while the replacement's stdin remains open.
        let mut completed = Vec::new();
        original_output.read_to_end(&mut completed)?;
        assert!(completed.contains(&b'S'));
        assert!(replacement.try_wait()?.is_none());
        assert_eq!(
            worker.stop_child("quit")?.map(|child| child.id()),
            Some(second)
        );
        Ok(())
    }

    #[test]
    #[cfg(windows)]
    fn one_restart_recovers_an_exited_failed_worker() -> io::Result<()> {
        // An invalid test harness option exits the disposable child with a failure status.
        let child = Command::new(std::env::current_exe()?)
            .arg("--invalid-inventory-test-option")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;
        let old = child.id();
        let system =
            std::env::var_os("SystemRoot").ok_or_else(|| io::Error::other("Missing SystemRoot"))?;
        let mut worker = Benchmark {
            child: Some(child),
            program: Some(Command::new(
                PathBuf::from(system).join("System32/sort.exe"),
            )),
            _pins: Vec::new(),
        };
        worker.restart(&AtomicBool::new(false))?;
        let replacement = worker.child.as_mut().unwrap();
        assert_ne!(old, replacement.id());
        assert!(replacement.try_wait()?.is_none());
        worker.stop_child("quit")?;
        Ok(())
    }

    #[test]
    fn quit_during_a_drain_supersedes_queued_restarts() -> io::Result<()> {
        const PORT: &str = "IFW_QA_WINDOWS_TEST_WORKER_DRAIN_PORT";
        let timeout = Duration::from_secs(5);
        if let Ok(value) = std::env::var(PORT) {
            // Run this same native test as the child, with a second channel independent of stdin.
            let port: u16 = value.parse().map_err(io::Error::other)?;
            let mut peer = TcpStream::connect((Ipv4Addr::LOCALHOST, port))?;
            peer.set_read_timeout(Some(timeout))?;
            peer.write_all(&std::process::id().to_le_bytes())?;
            let mut input = Vec::new();
            io::stdin().read_to_end(&mut input)?;
            assert_eq!(input, b"S");
            peer.write_all(b"D")?;
            let mut release = [0];
            peer.read_exact(&mut release)?;
            assert_eq!(&release, b"R");
            return Ok(());
        }

        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
        listener.set_nonblocking(true)?;
        let mut program = Command::new(std::env::current_exe()?);
        program
            .args([
                "--exact",
                "benchmark::tests::quit_during_a_drain_supersedes_queued_restarts",
            ])
            .env(PORT, listener.local_addr()?.port().to_string())
            .stdout(Stdio::null());
        let mut worker = Benchmark {
            child: None,
            program: Some(program),
            _pins: Vec::new(),
        };
        let first = worker.spawn_child()?;
        worker.release()?;
        let owner = Owner::new(worker, true)?;
        let requests = owner.restarts().unwrap();
        let deadline = Instant::now() + timeout;
        let mut peer = loop {
            match listener.accept() {
                Ok((peer, _)) => break peer,
                Err(error)
                    if error.kind() == io::ErrorKind::WouldBlock && Instant::now() < deadline =>
                {
                    thread::sleep(Duration::from_millis(10));
                }
                Err(error) => return Err(error),
            }
        };
        peer.set_read_timeout(Some(timeout))?;
        let mut pid = [0; 4];
        peer.read_exact(&mut pid)?;
        assert_eq!(u32::from_le_bytes(pid), first);
        requests.request();
        let mut draining = [0];
        peer.read_exact(&mut draining)?;
        assert_eq!(&draining, b"D");
        requests.request();
        requests.request();
        requests.begin_quit();
        peer.write_all(b"R")?;

        let (done, finished) = mpsc::sync_channel(1);
        thread::spawn(move || {
            let _ = done.send(owner.finish());
        });
        finished
            .recv_timeout(timeout * 2)
            .map_err(io::Error::other)??;
        requests.request();
        assert_eq!(peer.read(&mut draining)?, 0);
        assert_eq!(
            listener.accept().unwrap_err().kind(),
            io::ErrorKind::WouldBlock
        );
        Ok(())
    }
}
