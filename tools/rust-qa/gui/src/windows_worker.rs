//! Own the optional Windows inventory process on a disposable benchmark VM.
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

pub(super) struct Benchmark {
    child: Option<Child>,
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
                _pins: Vec::new(),
            });
        }
        let top = std::env::var_os("IFW_QA_INVENTORY_ROOT").map(PathBuf::from);
        let runner = std::env::var_os("RUNNER_TEMP").map(PathBuf::from);
        let exe = std::env::current_exe()?;
        let token = std::env::var("IFW_QA_INVENTORY_TOKEN").unwrap_or_default();
        let Some(top) = top else {
            return Err(io::Error::other("Missing private comparison root"));
        };
        if std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
            || std::env::var("GITHUB_ACTIONS").as_deref() != Ok("true")
            || std::env::var("RUNNER_ENVIRONMENT").as_deref() != Ok("github-hosted")
            || std::env::var("RUNNER_OS").as_deref() != Ok("Windows")
            || !top.is_absolute()
            || top.parent() != runner.as_deref()
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
        let child = Command::new(worker)
            .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
            .stdin(Stdio::piped())
            .spawn()?;
        let pid = child.id();
        let result = Self {
            child: Some(child),
            _pins: vec![root, staged, marker, image],
        };
        println!("INVENTORY_WORKER pid={pid}");
        Ok(result)
    }

    /// The existing tray bootstrap byte releases the worker after the observer attaches.
    pub(super) fn release(&mut self) -> io::Result<()> {
        if let Some(pipe) = self.child.as_mut().and_then(|child| child.stdin.as_mut()) {
            pipe.write_all(b"S")?;
        }
        Ok(())
    }

    pub(super) fn finish(mut self) -> io::Result<()> {
        if let Some(child) = self.child.as_mut() {
            drop(child.stdin.take());
            let status = wait_child(child, Duration::from_secs(6))?.ok_or_else(|| {
                io::Error::new(io::ErrorKind::TimedOut, "Inventory did not exit after EOF")
            })?;
            self.child.take();
            if !status.success() {
                return Err(io::Error::other("Native comparison inventory failed"));
            }
        }
        Ok(())
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
