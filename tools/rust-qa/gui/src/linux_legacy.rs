//! Hold the installed shipping socket while the elected Rust GUI owns the worker.
use std::fs::{self, File};
use std::io;
use std::net::Shutdown;
use std::os::fd::{AsRawFd, OwnedFd};
use std::os::unix::fs::{FileTypeExt, MetadataExt, OpenOptionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread::{self, JoinHandle};
use std::time::{Duration, SystemTime};

pub(super) const APP: &str = "io.github.voltkraft.immich-folder-watch";
const ENDPOINT: &str = "immich-folder-watch.sock";

pub(super) fn installed_runtime() -> io::Result<Option<Runtime>> {
    let declared = std::env::var_os("FLATPAK_ID");
    let metadata = match fs::read_to_string("/.flatpak-info") {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound && declared.is_none() => {
            return Ok(None);
        }
        Err(error) => return Err(error),
    };
    let app = application_name(&metadata)?;
    if declared
        .as_deref()
        .is_some_and(|name| name != std::ffi::OsStr::new(app))
    {
        return Err(io::Error::other(
            "Inconsistent installed application identity",
        ));
    }
    if app != APP {
        return Ok(None);
    }
    let uid = fs::metadata("/proc/self")?.uid();
    let runtime = PathBuf::from(format!("/run/user/{uid}"));
    if std::env::var_os("XDG_RUNTIME_DIR").as_deref() != Some(runtime.as_os_str()) {
        return Err(io::Error::other("Unexpected installed runtime directory"));
    }
    Runtime::open(&runtime, uid).map(Some)
}

fn application_name(metadata: &str) -> io::Result<&str> {
    let mut application = false;
    let mut name = None;
    for line in metadata.lines().map(str::trim) {
        if line.starts_with('[') {
            application = line == "[Application]";
            continue;
        }
        let Some(value) = line.strip_prefix("name=").filter(|_| application) else {
            continue;
        };
        if value.is_empty() || name.replace(value).is_some() {
            return Err(io::Error::other("Invalid installed application name"));
        }
    }
    name.ok_or_else(|| io::Error::other("Missing installed application name"))
}

fn identity(info: &fs::Metadata) -> (u64, u64) {
    (info.dev(), info.ino())
}

fn pin(path: &Path) -> io::Result<File> {
    // Linux O_PATH pins a filesystem node without opening any socket or FIFO for I/O.
    const O_PATH: i32 = 0x200000;
    File::options().read(true).custom_flags(O_PATH).open(path)
}

fn check_anchor(path: &Path, directory: &fs::Metadata) -> io::Result<()> {
    let anchor = fs::metadata(path)?;
    if !anchor.is_dir() || identity(&anchor) != identity(directory) {
        return Err(io::Error::other(
            "Cannot resolve the private runtime directory through its handle",
        ));
    }
    Ok(())
}

pub(super) struct Runtime {
    path: PathBuf,
    directory: File,
    uid: u32,
}

impl Runtime {
    fn open(path: &Path, uid: u32) -> io::Result<Self> {
        let runtime = Self {
            path: path.to_owned(),
            directory: pin(path)?,
            uid,
        };
        runtime.verify()?;
        Ok(runtime)
    }

    fn verify(&self) -> io::Result<()> {
        let named = fs::symlink_metadata(&self.path)?;
        let opened = self.directory.metadata()?;
        if !named.is_dir()
            || named.uid() != self.uid
            || named.mode() & 0o777 != 0o700
            || identity(&named) != identity(&opened)
        {
            return Err(io::Error::other(
                "Expected the original private current-user Flatpak runtime directory",
            ));
        }
        check_anchor(&self.anchor(), &opened)
    }

    fn anchor(&self) -> PathBuf {
        PathBuf::from(format!("/proc/self/fd/{}", self.directory.as_raw_fd()))
    }

    pub(super) fn claim(self) -> io::Result<Guard> {
        self.verify()?;
        let anchor = self.anchor();
        let nonce = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .map_err(io::Error::other)?
            .as_nanos();
        let staged = anchor.join(format!(".ifw-listener-{}-{nonce:x}", std::process::id()));
        let public = anchor.join(ENDPOINT);
        // Bind and listen at an exclusive staging name. The old store reclaims a
        // visible bound socket on ECONNREFUSED, including the interval before listen.
        let listener = UnixListener::bind(&staged)?;
        // A listener has a separate socketfs inode. Pin the filesystem socket before
        // publishing or removing any name. A failure here leaves the unpublished name alone.
        let created = fs::symlink_metadata(&staged)?;
        let node = pin(&staged)?;
        if !created.file_type().is_socket() || identity(&node.metadata()?) != identity(&created) {
            return Err(io::Error::other(
                "The unpublished listener changed before it could be pinned",
            ));
        }
        let mut guard = Guard {
            runtime: self,
            node,
            staged: Some(staged.clone()),
            public: None,
            rejector: None,
        };
        guard.check_name(&staged)?;
        guard.rejector = Some(Rejector::start(listener)?);
        guard.runtime.verify()?;
        fs::hard_link(&staged, &public).map_err(|error| {
            if error.kind() == io::ErrorKind::AlreadyExists {
                io::Error::new(
                    io::ErrorKind::AlreadyExists,
                    "Shipping activation endpoint is occupied. Startup refused.",
                )
            } else {
                error
            }
        })?;
        guard.public = Some(public.clone());
        guard.check_name(&public)?;
        guard.remove_owned(&staged)?;
        guard.staged = None;
        guard.runtime.verify()?;
        Ok(guard)
    }
}

pub(super) struct Guard {
    runtime: Runtime,
    node: File,
    staged: Option<PathBuf>,
    public: Option<PathBuf>,
    rejector: Option<Rejector>,
}

impl Guard {
    fn check_name(&self, name: &Path) -> io::Result<()> {
        let entry = fs::symlink_metadata(name)?;
        if !entry.file_type().is_socket() || identity(&entry) != identity(&self.node.metadata()?) {
            return Err(io::Error::other("Installed socket identity changed"));
        }
        Ok(())
    }

    fn remove_owned(&self, name: &Path) -> io::Result<()> {
        self.runtime.verify()?;
        self.check_name(name)?;
        fs::remove_file(name)
    }
}

impl Drop for Guard {
    fn drop(&mut self) {
        // Keep the listener open during removal: a normal old launcher cannot
        // reclaim this live node between our identity check and unlink.
        let mut released = self.public.is_some();
        for name in self.public.iter().chain(self.staged.iter()) {
            if let Err(error) = self.remove_owned(name) {
                released = false;
                if error.kind() != io::ErrorKind::NotFound {
                    eprintln!("Installed socket cleanup: {error}");
                }
            }
        }
        if let Some(rejector) = self.rejector.take() {
            match rejector.finish() {
                Ok(count) if released => println!("LEGACY_SOCKET_ACCEPTED {count}"),
                Ok(_) => {}
                Err(error) => eprintln!("Installed socket shutdown: {error}"),
            }
        }
    }
}

struct Rejector {
    stop: Arc<AtomicBool>,
    shutdown: UnixStream,
    worker: JoinHandle<u64>,
}

impl Rejector {
    fn start(listener: UnixListener) -> io::Result<Self> {
        // Linux shutdown on this duplicated listening descriptor wakes a blocking
        // accept without opening a connection or periodically waking the idle GUI.
        let shutdown = UnixStream::from(OwnedFd::from(listener.try_clone()?));
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = Arc::clone(&stop);
        let worker = thread::Builder::new()
            .name("legacy-socket".into())
            .spawn(move || {
                let mut count = 0_u64;
                while !stopping.load(Ordering::Acquire) {
                    // Keep just one accepted descriptor. Closing it requires no peer data or PID.
                    match listener.accept() {
                        Ok(_) => count = count.saturating_add(1),
                        Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
                        Err(_) if stopping.load(Ordering::Acquire) => break,
                        Err(_) => thread::park_timeout(Duration::from_millis(100)),
                    }
                }
                count
            })?;
        Ok(Self {
            stop,
            shutdown,
            worker,
        })
    }

    fn finish(self) -> io::Result<u64> {
        self.stop.store(true, Ordering::Release);
        self.worker.thread().unpark();
        self.shutdown.shutdown(Shutdown::Both)?;
        self.worker
            .join()
            .map_err(|_| io::Error::other("Installed socket receiver terminated unexpectedly"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    use std::os::unix::fs::{DirBuilderExt, symlink};
    use std::sync::Barrier;

    struct Private(PathBuf);

    impl Private {
        fn new(label: &str) -> io::Result<Self> {
            let path =
                std::env::temp_dir().join(format!("ifw-legacy-{}-{label}", std::process::id()));
            fs::DirBuilder::new().mode(0o700).create(&path)?;
            Ok(Self(path))
        }

        fn runtime(&self) -> io::Result<Runtime> {
            Runtime::open(&self.0, fs::metadata(&self.0)?.uid())
        }
    }

    impl Drop for Private {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn application_identity_uses_the_application_section() {
        assert_eq!(application_name("[Application]\nruntime=runtime/example\nname=org.example.Test\n[Instance]\nname=other").unwrap(), "org.example.Test");
        assert!(application_name("[Instance]\nname=other").is_err());
        assert!(application_name("[Application]\nname=one\nname=two").is_err());
    }

    #[test]
    fn occupied_live_stale_file_and_link_are_preserved() -> io::Result<()> {
        let dir = Private::new("occupied")?;
        let leaf = dir.0.join(ENDPOINT);
        let occupied = || -> io::Result<()> {
            let before = identity(&fs::symlink_metadata(&leaf)?);
            assert_eq!(
                dir.runtime()?.claim().err().unwrap().kind(),
                io::ErrorKind::AlreadyExists
            );
            assert_eq!(before, identity(&fs::symlink_metadata(&leaf)?));
            assert_eq!(fs::read_dir(&dir.0)?.count(), 1);
            Ok(())
        };
        let listener = UnixListener::bind(&leaf)?;
        occupied()?;
        drop(listener);
        occupied()?;
        fs::remove_file(&leaf)?;
        fs::write(&leaf, b"fixture")?;
        occupied()?;
        assert_eq!(fs::read(&leaf)?, b"fixture");
        fs::remove_file(&leaf)?;
        symlink("absent", &leaf)?;
        occupied()?;
        assert_eq!(fs::read_link(&leaf)?, PathBuf::from("absent"));
        fs::remove_file(leaf)
    }

    #[test]
    fn competing_claims_publish_one_listening_socket_and_drain_idle_connections() -> io::Result<()>
    {
        let dir = Private::new("compete")?;
        let gate = Arc::new(Barrier::new(2));
        let handles = [dir.runtime()?, dir.runtime()?].map(|runtime| {
            let gate = Arc::clone(&gate);
            thread::spawn(move || {
                gate.wait();
                runtime.claim()
            })
        });
        let [left, right] = handles.map(|h| h.join().unwrap());
        let (guard, refused) = match (left, right) {
            (Ok(guard), Err(error)) | (Err(error), Ok(guard)) => (guard, error),
            _ => panic!("expected exactly one exclusive claim"),
        };
        assert_eq!(refused.kind(), io::ErrorKind::AlreadyExists);
        let leaf = dir.0.join(ENDPOINT);
        let mut pending = UnixStream::connect(&leaf)?;
        for _ in 0..16 {
            let mut probe = UnixStream::connect(&leaf)?;
            probe.set_read_timeout(Some(Duration::from_secs(2)))?;
            assert_eq!(probe.read(&mut [0])?, 0);
        }
        pending.set_read_timeout(Some(Duration::from_secs(2)))?;
        assert_eq!(pending.read(&mut [0])?, 0);
        drop(guard);
        assert_eq!(fs::read_dir(&dir.0)?.count(), 0);
        drop(UnixListener::bind(&leaf)?);
        fs::remove_file(leaf)
    }

    #[test]
    fn cleanup_keeps_a_replacement_socket_and_admission_requires_the_original_directory()
    -> io::Result<()> {
        let dir = Private::new("replacement")?;
        let leaf = dir.0.join(ENDPOINT);
        let guard = dir.runtime()?.claim()?;
        fs::remove_file(&leaf)?;
        let replacement = UnixListener::bind(&leaf)?;
        let expected = identity(&fs::symlink_metadata(&leaf)?);
        drop(guard);
        assert_eq!(identity(&fs::symlink_metadata(&leaf)?), expected);
        drop(replacement);
        fs::remove_file(&leaf)?;
        let runtime = dir.runtime()?;
        let opened = runtime.directory.metadata()?;
        assert!(check_anchor(&dir.0.join("missing"), &opened).is_err());
        assert!(check_anchor(dir.0.parent().unwrap(), &opened).is_err());
        let moved = dir.0.with_extension("moved");
        fs::rename(&dir.0, &moved)?;
        fs::DirBuilder::new().mode(0o700).create(&dir.0)?;
        assert!(runtime.claim().is_err());
        assert_eq!(fs::read_dir(&moved)?.count(), 0);
        fs::remove_dir(moved)
    }

    #[test]
    fn private_bus_disconnect_preserves_the_shipping_endpoint_until_supervisor_shutdown()
    -> Result<(), Box<dyn std::error::Error>> {
        use crate::Control;
        use crate::linux::{Primary, menu, watcher::Watcher};
        use std::io::{BufRead, BufReader};
        use std::process::{Child, Command, Stdio};
        struct Bus(Child);
        impl Drop for Bus {
            fn drop(&mut self) {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }
        let dir = Private::new("bus-loss")?;
        let address = format!("unix:path={}", dir.0.join("private-bus").display());
        let config = dir.0.join("session.conf");
        fs::write(
            &config,
            format!(
                "<busconfig><type>session</type><listen>{address}</listen><policy context='default'><allow user='*'/><allow send_destination='*'/><allow receive_sender='*'/></policy></busconfig>"
            ),
        )?;
        let mut bus = Bus(Command::new("dbus-daemon")
            .arg("--nofork")
            .arg("--print-address=1")
            .arg(format!("--config-file={}", config.display()))
            .stdout(Stdio::piped())
            .spawn()?);
        let mut announced = String::new();
        BufReader::new(bus.0.stdout.take().unwrap()).read_line(&mut announced)?;
        assert!(announced.trim().starts_with(&format!("{address},guid=")));
        let connection = futures_lite::future::block_on(
            zbus::connection::Builder::address(announced.trim())?.build(),
        )?;
        let guard = dir.runtime()?.claim()?;
        let (sender, _commands) = std::sync::mpsc::sync_channel(1);
        let control = Control {
            sender,
            window: Default::default(),
            graphics_attention: Default::default(),
            appearance: Default::default(),
        };
        let watcher = futures_lite::future::block_on(Watcher::start(
            &connection,
            control,
            crate::linux::INSTALLED_NAME,
        ));
        let publisher = menu::Publisher::new(connection.clone(), Default::default());
        let primary = Primary {
            connection,
            installed_socket: Some(guard),
            publisher,
            watcher,
        };
        // Retaining a language control across bus loss must allow the primary to drain.
        let language = primary.tray_language();
        language.set_german(false);
        bus.0.kill()?;
        bus.0.wait()?;
        futures_lite::future::block_on(primary.closed());
        let leaf = dir.0.join(ENDPOINT);
        let mut probe = UnixStream::connect(&leaf)?;
        probe.set_read_timeout(Some(Duration::from_secs(2)))?;
        assert_eq!(probe.read(&mut [0])?, 0);
        futures_lite::future::block_on(primary.graceful_shutdown());
        language.set_german(true);
        assert!(!leaf.try_exists()?);
        fs::remove_file(config)?;
        // The deliberately terminated daemon may leave its private bus socket.
        if dir.0.join("private-bus").try_exists()? {
            fs::remove_file(dir.0.join("private-bus"))?;
        }
        Ok(())
    }
}
