use super::staging::transaction_name;
use super::{Directory, EntryKind, FileIdentity, ObjectInfo, denied};
use std::collections::VecDeque;
use std::ffi::{CString, OsStr, OsString, c_char, c_int};
use std::fs::{File, OpenOptions};
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;
use std::sync::{Arc, Mutex};

// Linux UAPI differs between x86_64 and arm64 for these two flags.
#[cfg(target_arch = "x86_64")]
const O_DIRECTORY: c_int = 0x10000;
#[cfg(target_arch = "x86_64")]
const O_NOFOLLOW: c_int = 0x20000;
#[cfg(target_arch = "aarch64")]
const O_DIRECTORY: c_int = 0x4000;
#[cfg(target_arch = "aarch64")]
const O_NOFOLLOW: c_int = 0x8000;
const O_CLOEXEC: c_int = 0x80000;
const O_NONBLOCK: c_int = 0x800;
const O_PATH: c_int = 0x200000;

// The stable 256-byte kernel UAPI reserves the tail for extension. The
// filesystem reports which requested fields it could actually supply.
#[derive(Default)]
#[repr(C)]
struct Statx {
    mask: u32,
    _block_size: u32,
    _attributes: u64,
    links: u32,
    uid: u32,
    _gid: u32,
    mode: u16,
    _spare: u16,
    inode: u64,
    _size_blocks_times_and_rdev: [u64; 12],
    device_major: u32,
    device_minor: u32,
    _remaining: [u64; 14],
}

const _: () = assert!(size_of::<Statx>() == 256);
const _: () = assert!(std::mem::offset_of!(Statx, device_major) == 136);
const _: () = assert!(std::mem::offset_of!(Statx, inode) == 32);

unsafe extern "C" {
    fn openat(dirfd: c_int, path: *const c_char, flags: c_int, ...) -> c_int;
    fn mkdirat(dirfd: c_int, path: *const c_char, mode: u32) -> c_int;
    fn unlinkat(dirfd: c_int, path: *const c_char, flags: c_int) -> c_int;
    fn renameat2(
        from_fd: c_int,
        from: *const c_char,
        to_fd: c_int,
        to: *const c_char,
        flags: u32,
    ) -> c_int;
    fn geteuid() -> u32;
    fn statx(dirfd: c_int, path: *const c_char, flags: c_int, mask: u32, info: *mut Statx)
    -> c_int;
}

pub(super) fn open_root(path: &Path) -> io::Result<File> {
    OpenOptions::new()
        .read(true)
        .custom_flags(O_DIRECTORY | O_NOFOLLOW)
        .open(path)
}

fn open_at(parent: &File, name: &OsStr, flags: c_int) -> io::Result<File> {
    let name = CString::new(name.as_bytes())?;
    // SAFETY: parent is borrowed throughout, name is NUL-terminated and the
    // mode is supplied for creation. A successful result is a fresh owned fd.
    let fd = unsafe {
        openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | O_CLOEXEC | O_NOFOLLOW,
            0o600_u32,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: ownership of this new descriptor has not been transferred yet.
    Ok(unsafe { File::from_raw_fd(fd) })
}

pub(super) fn open_directory(parent: &File, name: &OsStr) -> io::Result<File> {
    open_at(parent, name, O_DIRECTORY)
}

fn stat_handle(file: &File, required: u32) -> io::Result<Statx> {
    let mut metadata = Statx::default();
    // SAFETY: AT_EMPTY_PATH queries this borrowed descriptor. The buffer has
    // the UAPI size and alignment on both supported targets.
    if unsafe {
        statx(
            file.as_raw_fd(),
            c"".as_ptr(),
            0x1000,
            required,
            &mut metadata,
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    if metadata.mask & required != required {
        return Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "filesystem omitted required identity or metadata fields",
        ));
    }
    Ok(metadata)
}

pub(super) fn info(file: &File) -> io::Result<ObjectInfo> {
    // Match the legacy required field mask and also require ctime.
    let metadata = stat_handle(file, 0x747 | 0x80)?;
    let kind = match metadata.mode & 0xf000 {
        0x8000 => EntryKind::File,
        0x4000 => EntryKind::Directory,
        0xa000 => return Err(denied("symbolic links are outside the watch grant")),
        _ => EntryKind::Other,
    };
    Ok(ObjectInfo {
        kind,
        identity: FileIdentity {
            volume: (u64::from(metadata.device_major) << 32) | u64::from(metadata.device_minor),
            file: metadata.inode.into(),
        },
        links: metadata.links.into(),
    })
}

pub(super) fn entry_info(parent: &File, name: &OsStr) -> io::Result<ObjectInfo> {
    info(&open_at(parent, name, O_PATH)?)
}

fn proc_fd(file: &File) -> String {
    format!("/proc/self/fd/{}", file.as_raw_fd())
}

pub(super) fn open_file(parent: &File, name: &OsStr, _writable_times: bool) -> io::Result<File> {
    let pinned = open_at(parent, name, O_PATH)?;
    let selected = info(&pinned)?;
    selected.require(EntryKind::File)?;
    // The procfs magic link names this still-live fd. The original media name
    // can change here without selecting another object.
    let readable = OpenOptions::new()
        .read(true)
        .custom_flags(O_NONBLOCK)
        .open(proc_fd(&pinned))?;
    if info(&readable)?.identity != selected.identity {
        return Err(denied(
            "media identity changed while acquiring a read handle",
        ));
    }
    readable.try_lock_shared()?;
    Ok(readable)
}

pub(super) fn enumerate(
    file: &File,
    mut visit: impl FnMut(OsString) -> io::Result<()>,
) -> io::Result<()> {
    // read_dir opens a separate cursor on the pinned directory. The borrowing
    // File outlives traversal, so its descriptor number cannot be reused.
    for entry in std::fs::read_dir(proc_fd(file))? {
        visit(entry?.file_name())?;
    }
    Ok(())
}

pub(super) fn random_bytes() -> io::Result<[u8; 16]> {
    let mut bytes = [0; 16];
    File::open("/dev/urandom")?.read_exact(&mut bytes)?;
    Ok(bytes)
}

fn private_directory(parent: &File) -> io::Result<(OsString, File)> {
    let name = transaction_name()?;
    let c_name = CString::new(name.as_bytes())?;
    // SAFETY: both parent and name are live until the synchronous call returns.
    if unsafe { mkdirat(parent.as_raw_fd(), c_name.as_ptr(), 0o700) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let file = open_directory(parent, &name)?;
    require_private(&file)?;
    Ok((name, file))
}

fn require_private(directory: &File) -> io::Result<()> {
    let meta = stat_handle(directory, 0xb)?; // type, mode and owner
    // SAFETY: querying the effective uid takes no pointers.
    if meta.mode & 0xf000 != 0x4000
        || meta.uid != unsafe { geteuid() }
        || meta.mode & 0o777 != 0o700
    {
        // Its protection could not be established. Leave this name alone.
        return Err(denied(
            "transaction filesystem must enforce owner-only directory access",
        ));
    }
    Ok(())
}

#[derive(Debug)]
struct Container {
    parent_id: FileIdentity,
    _parent: File,
    directory: Arc<File>,
}

#[derive(Debug, Default)]
pub(super) struct Containers(Mutex<VecDeque<Container>>);

impl Containers {
    fn for_parent(&self, parent: &File) -> io::Result<Arc<File>> {
        let parent_id = info(parent)?.identity;
        let mut entries = self
            .0
            .lock()
            .map_err(|_| io::Error::other("transaction cache interrupted"))?;
        let entry = if let Some(index) = entries.iter().position(|e| e.parent_id == parent_id) {
            entries
                .remove(index)
                .expect("index is from this locked cache")
        } else {
            let (_, directory) = private_directory(parent)?;
            if entries.len() == 64 {
                // Directory names in shared parents cannot be removed by inode.
                // Active transactions still hold their own Arc to the container.
                entries.pop_front();
            }
            Container {
                parent_id,
                _parent: parent.try_clone()?,
                directory: Arc::new(directory),
            }
        };
        let directory = Arc::clone(&entry.directory);
        entries.push_back(entry);
        Ok(directory)
    }
}

fn check_entry(parent: &File, name: &OsStr, expected: &File) -> io::Result<()> {
    if entry_info(parent, name)?.identity != info(expected)?.identity {
        return Err(denied("private transaction entry changed identity"));
    }
    Ok(())
}

fn unlink_private(parent: &File, name: &OsStr, expected: &File, flags: c_int) -> io::Result<()> {
    require_private(parent)?;
    check_entry(parent, name, expected)?;
    let name = CString::new(name.as_bytes())?;
    // SAFETY: this parent was verified 0700 under our uid; the expected object
    // and its parent stay live. There is no unlink from a shared media parent.
    if unsafe { unlinkat(parent.as_raw_fd(), name.as_ptr(), flags) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

#[derive(Debug)]
pub(super) struct Transaction {
    outer: Arc<File>,
    directory: File,
    name: OsString,
}

impl Transaction {
    pub(super) fn new(parent: &Directory) -> io::Result<Self> {
        let outer = parent.0.containers.for_parent(&parent.0.file)?;
        require_private(&outer)?;
        let (name, directory) = private_directory(&outer)?;
        Ok(Self {
            outer,
            directory,
            name,
        })
    }

    pub(super) fn create_payload(&self) -> io::Result<File> {
        open_at(&self.directory, OsStr::new("payload"), 2 | 0x40 | 0x80) // O_RDWR | O_CREAT | O_EXCL
    }

    pub(super) fn rename_payload(
        &self,
        file: &File,
        destination: &File,
        name: &OsStr,
    ) -> io::Result<()> {
        require_private(&self.directory)?;
        check_entry(&self.directory, OsStr::new("payload"), file)?;
        let name = CString::new(name.as_bytes())?;
        // SAFETY: the source name is inside the protected directory. Both
        // directories are pinned. RENAME_NOREPLACE is the atomic collision gate.
        if unsafe {
            renameat2(
                self.directory.as_raw_fd(),
                c"payload".as_ptr(),
                destination.as_raw_fd(),
                name.as_ptr(),
                1,
            )
        } != 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }

    pub(super) fn sync_rename(&self, destination: &File) -> io::Result<()> {
        destination.sync_all()?;
        self.directory.sync_all()
    }

    pub(super) fn remove_payload(&self, expected: &File) -> io::Result<()> {
        unlink_private(&self.directory, OsStr::new("payload"), expected, 0)
    }

    pub(super) fn remove_directory(self) -> io::Result<()> {
        unlink_private(&self.outer, &self.name, &self.directory, 0x200) // AT_REMOVEDIR
    }
}
