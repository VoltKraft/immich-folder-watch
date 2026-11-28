//! Own the optional Windows inventory process on a disposable benchmark VM.
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{self, SyncSender, TrySendError};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

pub(super) struct Benchmark {
    child: Option<Child>,
    executable: Option<PathBuf>,
    _pins: Vec<File>,
}

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
    pub(super) fn start() -> io::Result<Self> {
        if std::env::var("IFW_QA_BENCHMARK").as_deref() != Ok("1") {
            return Ok(Self {
                child: None,
                executable: None,
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
        let mut result = Self {
            child: None,
            executable: Some(worker),
            _pins: vec![root, staged, marker, image],
        };
        result.spawn_child()?;
        Ok(result)
    }

    fn spawn_child(&mut self) -> io::Result<u32> {
        let path = self
            .executable
            .as_ref()
            .ok_or_else(|| io::Error::other("Missing pinned inventory executable"))?;
        if self.child.is_some() {
            return Err(io::Error::other(
                "Previous inventory process is still owned",
            ));
        }
        let child = Command::new(path)
            .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
            .stdin(Stdio::piped())
            .spawn()?;
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
            if !status.success() {
                return Err(io::Error::other("Native comparison inventory failed"));
            }
            return Ok(reaped);
        }
        Ok(None)
    }

    fn restart(&mut self) -> io::Result<()> {
        let old = self.stop_child("restart")?;
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

pub(super) enum WorkerCommand {
    Restart,
    Stop,
}

pub(super) struct Restarts(SyncSender<WorkerCommand>);

impl Restarts {
    pub(super) fn request(&self) {
        match self.0.try_send(WorkerCommand::Restart) {
            Ok(()) => (),
            Err(TrySendError::Full(_)) => println!("WORKER_RESTART_PENDING"),
            Err(TrySendError::Disconnected(_)) => {
                eprintln!("WORKER_RESTART_FAILED owner disconnected")
            }
        }
    }
}

pub(super) enum Owner {
    Direct(Benchmark),
    Tray(SyncSender<WorkerCommand>, JoinHandle<io::Result<()>>),
}

impl Owner {
    pub(super) fn new(mut worker: Benchmark, with_tray: bool) -> io::Result<Self> {
        if !with_tray {
            return Ok(Self::Direct(worker));
        }
        let (send, commands) = mpsc::sync_channel(1);
        let thread = thread::Builder::new()
            .name("windows-inventory-owner".into())
            .spawn(move || {
                while let Ok(WorkerCommand::Restart) = commands.recv() {
                    if let Err(error) = worker.restart() {
                        eprintln!("WORKER_RESTART_FAILED {error}");
                    }
                }
                worker.stop_child("quit")?;
                Ok(())
            })?;
        Ok(Self::Tray(send, thread))
    }

    pub(super) fn restarts(&self) -> Option<Restarts> {
        match self {
            Self::Tray(send, _) => Some(Restarts(send.clone())),
            Self::Direct(_) => None,
        }
    }

    pub(super) fn finish(self) -> io::Result<()> {
        match self {
            Self::Direct(mut worker) => {
                worker.stop_child("quit")?;
                Ok(())
            }
            Self::Tray(send, thread) => {
                let _ = send.send(WorkerCommand::Stop);
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

    #[test]
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
            executable: Some(sorter),
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
        worker.restart()?;
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
    fn failed_original_stops_restart_before_spawning_replacement() -> io::Result<()> {
        // An invalid test harness option exits the disposable child with a failure status.
        let child = Command::new(std::env::current_exe()?)
            .arg("--invalid-inventory-test-option")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;
        let mut worker = Benchmark {
            child: Some(child),
            executable: None,
            _pins: Vec::new(),
        };
        assert_eq!(
            worker.restart().unwrap_err().to_string(),
            "Native comparison inventory failed"
        );
        assert!(worker.child.is_none());
        Ok(())
    }
}
