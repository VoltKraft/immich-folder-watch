use super::{Reason, Scope, Shared};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{CString, c_char, c_int, c_short, c_ulong};
use std::fs::File;
use std::io::{self, PipeReader, PipeWriter, Read};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::sync::Arc;
use std::sync::mpsc::SyncSender;

const NONBLOCK: c_int = 0o4000;
const CLOEXEC: c_int = 0o2000000;
const MODIFY: u32 = 0x02;
const ATTRIB: u32 = 0x04;
const CLOSE_WRITE: u32 = 0x08;
const MOVED_FROM: u32 = 0x40;
const MOVED_TO: u32 = 0x80;
const CREATE: u32 = 0x100;
const DELETE: u32 = 0x200;
const DELETE_SELF: u32 = 0x400;
const MOVE_SELF: u32 = 0x800;
const UNMOUNT: u32 = 0x2000;
const Q_OVERFLOW: u32 = 0x4000;
const IGNORED: u32 = 0x8000;
const ONLYDIR: u32 = 0x0100_0000;
const ISDIR: u32 = 0x4000_0000;
const NAMES: u32 = MOVED_FROM | MOVED_TO | CREATE | DELETE;
const MASK: u32 = NAMES | MODIFY | ATTRIB | CLOSE_WRITE | DELETE_SELF | MOVE_SELF | ONLYDIR;
const MAX_DIRECTORIES: usize = 1024;
const POLLIN: c_short = 1;

#[repr(C)]
struct PollFd {
    fd: c_int,
    events: c_short,
    revents: c_short,
}

unsafe extern "C" {
    fn inotify_init1(flags: c_int) -> c_int;
    fn inotify_add_watch(fd: c_int, path: *const c_char, mask: u32) -> c_int;
    fn poll(fds: *mut PollFd, count: c_ulong, timeout_ms: c_int) -> c_int;
}

fn add(events: &File, directory: &File) -> io::Result<()> {
    // The only name resolved is the live descriptor in this process's procfs.
    let path = CString::new(format!("/proc/self/fd/{}", directory.as_raw_fd())).unwrap();
    // SAFETY: both descriptors and the NUL-terminated string live across the call.
    if unsafe { inotify_add_watch(events.as_raw_fd(), path.as_ptr(), MASK) } == -1 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

pub(super) struct Stop(Option<PipeWriter>);

impl Stop {
    pub(super) fn signal(&mut self) -> io::Result<()> {
        // Closing the sole writer wakes the poller even in a network-free sandbox.
        self.0.take();
        Ok(())
    }
}

pub(super) struct Backend {
    events: File,
    stop: PipeReader,
    tree: bool,
    pub(super) registration: Arc<Registration>,
}

type Identity = (u64, u64);

fn identity(file: &File) -> io::Result<Identity> {
    let metadata = file.metadata()?;
    Ok((metadata.dev(), metadata.ino()))
}

pub(super) struct Registration {
    root: Identity,
    // Retaining each registered inode prevents reuse while identities are compared.
    directories: BTreeMap<Identity, File>,
}

impl Registration {
    fn add(&mut self, events: &File, directory: &File) -> io::Result<()> {
        let key = identity(directory)?;
        if let std::collections::btree_map::Entry::Vacant(entry) = self.directories.entry(key) {
            let retained = directory.try_clone()?;
            add(events, &retained)?;
            entry.insert(retained);
        }
        Ok(())
    }

    pub(super) fn matches(&self, root: &File, descendants: &[File]) -> io::Result<bool> {
        if descendants.len() >= MAX_DIRECTORIES || identity(root)? != self.root {
            return Ok(false);
        }
        let mut current = BTreeSet::from([self.root]);
        for directory in descendants {
            current.insert(identity(directory)?);
        }
        Ok(self.directories.keys().eq(current.iter()))
    }
}

pub(super) fn prepare(
    directory: &File,
    scope: Scope<'_>,
    shared: &Shared,
) -> io::Result<(Stop, Backend)> {
    // SAFETY: the flags are valid for inotify_init1 on the supported Linux targets.
    let fd = unsafe { inotify_init1(CLOEXEC | NONBLOCK) };
    if fd == -1 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: success transfers the sole owned descriptor to this File.
    let events = unsafe { File::from_raw_fd(fd) };
    let mut registration = Registration {
        root: identity(directory)?,
        directories: BTreeMap::new(),
    };
    registration.add(&events, directory)?;
    let tree = matches!(scope, Scope::Tree { .. });
    if let Scope::Tree { descendants, .. } = scope {
        let remaining = MAX_DIRECTORIES - 1;
        let mut incomplete = descendants.len() > remaining;
        for child in descendants.iter().take(remaining) {
            // A failing directory leaves the other established watches usable.
            incomplete |= registration.add(&events, child).is_err();
        }
        if incomplete {
            shared.record(Reason::CoverageIncomplete);
        }
    }
    let (stop, sender) = io::pipe()?;
    Ok((
        Stop(Some(sender)),
        Backend {
            events,
            stop,
            tree,
            registration: Arc::new(registration),
        },
    ))
}

fn decode(mut data: &[u8], tree: bool, shared: &Shared) -> io::Result<()> {
    while !data.is_empty() {
        let header = data
            .get(..16)
            .ok_or_else(|| io::Error::other("truncated inotify header"))?;
        let mask = u32::from_ne_bytes(header[4..8].try_into().unwrap());
        let name_len = u32::from_ne_bytes(header[12..16].try_into().unwrap()) as usize;
        data = data
            .get(16 + name_len..)
            .ok_or_else(|| io::Error::other("truncated inotify name"))?;
        // The source ID is implicit. An event name never crosses this boundary.
        let reason = if mask & Q_OVERFLOW != 0 {
            Reason::NativeOverflow
        } else if mask & (DELETE_SELF | MOVE_SELF | UNMOUNT | IGNORED) != 0 {
            Reason::WatchLost
        } else if tree && mask & ISDIR != 0 && mask & NAMES != 0 {
            Reason::TreeChanged
        } else {
            Reason::Changed
        };
        shared.record(reason);
    }
    Ok(())
}

impl Backend {
    pub(super) fn run(mut self, shared: &Shared, ready: SyncSender<()>) -> io::Result<()> {
        ready
            .send(())
            .map_err(|_| io::Error::other("watch owner exited"))?;
        let mut fds = [
            PollFd {
                fd: self.stop.as_raw_fd(),
                events: POLLIN,
                revents: 0,
            },
            PollFd {
                fd: self.events.as_raw_fd(),
                events: POLLIN,
                revents: 0,
            },
        ];
        let mut buffer = [0u8; 8192];
        loop {
            // SAFETY: poll may update only these two initialized live descriptors' revents.
            if unsafe { poll(fds.as_mut_ptr(), 2, -1) } == -1 {
                let error = io::Error::last_os_error();
                if error.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(error);
            }
            if fds[0].revents != 0 {
                return Ok(());
            }
            if fds[1].revents != POLLIN {
                return Err(io::Error::other("inotify subscription became unavailable"));
            }
            match self.events.read(&mut buffer) {
                Ok(0) => return Err(io::Error::other("inotify subscription closed")),
                Ok(len) => decode(&buffer[..len], self.tree, shared)?,
                Err(e)
                    if matches!(
                        e.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) => {}
                Err(e) => return Err(e),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn linux_kernel_overflow_record_survives_full_application_queue() {
        let shared = Shared::new(1);
        shared.record(Reason::Changed);
        let mut header = [0; 16];
        header[..4].copy_from_slice(&(-1i32).to_ne_bytes());
        header[4..8].copy_from_slice(&Q_OVERFLOW.to_ne_bytes());
        decode(&header, true, &shared).unwrap();
        let state = shared.state.lock().unwrap().snapshot;
        assert!(state.contains(Reason::NativeOverflow));
        assert!(state.contains(Reason::QueueFull));
        assert!(state.requires_registration);
        assert_eq!(state.queued, 1);
    }

    #[test]
    fn malformed_record_is_reported() {
        let mut record = [0; 16];
        record[12..16].copy_from_slice(&12u32.to_ne_bytes());
        assert!(decode(&record, false, &Shared::new(1)).is_err());
    }
}
