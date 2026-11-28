use super::{SIGNAL, TIMEOUT, announce};
use std::fs;
use std::io::{self, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::MetadataExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::time::{Duration, Instant};

const SOCKET: &str = "immich-folder-watch.sock";

#[repr(C)]
#[derive(Default)]
struct Credentials {
    pid: i32,
    uid: u32,
    gid: u32,
}

unsafe extern "C" {
    fn geteuid() -> u32;
    fn getsockopt(
        fd: i32,
        level: i32,
        option: i32,
        value: *mut Credentials,
        length: *mut u32,
    ) -> i32;
}

pub fn check_environment(root: &Path, owner: &str, _: &str) -> io::Result<()> {
    let metadata = fs::symlink_metadata(root)?;
    if owner != "unix"
        || !metadata.is_dir()
        || metadata.mode() & 0o077 != 0
        || metadata.uid() != unsafe { geteuid() }
    {
        return Err(io::Error::other(
            "expected a private current-user fixture directory",
        ));
    }
    Ok(())
}

fn check_peer(stream: &UnixStream, expected_pid: u32) -> io::Result<()> {
    let mut credentials = Credentials::default();
    let mut length = size_of::<Credentials>() as u32;
    // Linux SOL_SOCKET / SO_PEERCRED. The kernel supplies the connected process identity.
    if unsafe { getsockopt(stream.as_raw_fd(), 1, 17, &mut credentials, &mut length) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if length as usize != size_of::<Credentials>()
        || u32::try_from(credentials.pid) != Ok(expected_pid)
        || credentials.uid != unsafe { geteuid() }
    {
        return Err(io::Error::other("unexpected local activation peer"));
    }
    Ok(())
}

pub fn signal(root: &Path, _: &str, peer: u32) -> io::Result<()> {
    let mut stream = UnixStream::connect(root.join(SOCKET))?;
    check_peer(&stream, peer)?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    stream.write_all(SIGNAL)?;
    announce("SECONDARY_SIGNALLED")
}

pub fn listen(root: &Path, _: &str, peer: u32) -> io::Result<()> {
    let path = root.join(SOCKET);
    let listener = UnixListener::bind(&path)?;
    let bound = fs::symlink_metadata(&path)?;
    listener.set_nonblocking(true)?;
    announce("PRIMARY_READY")?;
    let deadline = Instant::now() + TIMEOUT;
    while Instant::now() < deadline {
        let stream = match listener.accept() {
            Ok((stream, _)) => stream,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(10));
                continue;
            }
            Err(error) => return Err(error),
        };
        check_peer(&stream, peer)?;
        stream.set_read_timeout(Some(Duration::from_secs(2)))?;
        let mut bytes = Vec::new();
        stream.take(65).read_to_end(&mut bytes)?;
        if bytes.is_empty() {
            // The shipping coordinator connects once to distinguish a live listener from a stale socket.
            continue;
        }
        if bytes != SIGNAL {
            return Err(io::ErrorKind::InvalidData.into());
        }
        let current = fs::symlink_metadata(&path)?;
        if (bound.dev(), bound.ino()) != (current.dev(), current.ino()) {
            return Err(io::Error::other(
                "fixture endpoint changed before clean shutdown",
            ));
        }
        fs::remove_file(path)?;
        return announce("SHOW_GUI");
    }
    Err(io::ErrorKind::TimedOut.into())
}
