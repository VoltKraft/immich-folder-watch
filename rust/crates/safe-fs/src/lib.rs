//! Handle-bound operations beneath a configured media directory.
//!
//! Only acquisition of the configured root resolves an absolute pathname. Each
//! child operation takes one native name relative to a retained parent. A
//! directory may be renamed while open on Linux. Its replacement receives no
//! authority from the original pathname.

use std::ffi::{OsStr, OsString};
use std::fs::{File, FileTimes, Metadata};
use std::io::{self, Read, Seek, SeekFrom};
use std::path::{Component, Path, PathBuf};
use std::sync::Arc;
use std::time::SystemTime;

#[cfg(not(all(
    any(target_os = "linux", windows),
    any(target_arch = "x86_64", target_arch = "aarch64")
)))]
compile_error!("safe-fs requires Linux or Windows on x86_64 or aarch64");

#[cfg(target_os = "linux")]
#[path = "linux.rs"]
mod native;

mod staging;
pub use staging::{Download, PublishError};
#[cfg(windows)]
#[path = "windows.rs"]
mod native;

const INTERNAL_PREFIX: &[u8] = b".ifw-internal-";

fn internal_name(name: &OsStr) -> bool {
    name.as_encoded_bytes()
        .split(|b| matches!(b, b'/' | b'\\'))
        .any(|part| {
            part.get(..INTERNAL_PREFIX.len())
                .is_some_and(|prefix| prefix.eq_ignore_ascii_case(INTERNAL_PREFIX))
        })
}

fn validate_child(name: &OsStr) -> io::Result<()> {
    let bytes = name.as_encoded_bytes();
    if bytes.is_empty()
        || matches!(bytes, b"." | b"..")
        || bytes.contains(&0)
        || bytes.contains(&b'/')
        || internal_name(name)
        || (cfg!(windows)
            && (bytes.contains(&b'\\')
                || bytes.contains(&b':')
                || bytes.ends_with(b" ")
                || bytes.ends_with(b".")))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "expected one authorized child name",
        ));
    }
    Ok(())
}

fn denied(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, reason)
}

/// An OS object identifier is comparable only while the selected object is pinned.
/// It carries no authority to mutate a file after closing its handle.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FileIdentity {
    volume: u64,
    file: u128,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EntryKind {
    Directory,
    File,
    Other,
}

#[derive(Debug)]
struct ObjectInfo {
    kind: EntryKind,
    identity: FileIdentity,
    links: u64,
}

impl ObjectInfo {
    fn require(&self, kind: EntryKind) -> io::Result<()> {
        if self.kind != kind {
            return Err(denied("unexpected filesystem object type"));
        }
        Ok(())
    }
}

#[derive(Debug, Eq, PartialEq)]
pub struct Entry {
    pub name: OsString,
    pub kind: EntryKind,
}

#[derive(Debug)]
struct DirectoryHandles {
    file: File,
    // Windows pins the ancestors against rename for the lifetime of this lease.
    _parent: Option<Directory>,
    #[cfg(target_os = "linux")]
    containers: Arc<native::Containers>,
    #[cfg(windows)]
    enumeration: std::sync::Mutex<()>,
}

/// A pinned directory and its ancestor handles. Cloning shares the capability
/// with a queued operation without opening any names again.
#[derive(Clone, Debug)]
pub struct Directory(Arc<DirectoryHandles>);

impl Directory {
    fn from_file(file: File, parent: Option<Self>) -> io::Result<Self> {
        native::info(&file)?.require(EntryKind::Directory)?;
        #[cfg(target_os = "linux")]
        let containers = parent
            .as_ref()
            .map(|p| Arc::clone(&p.0.containers))
            .unwrap_or_default();
        Ok(Self(Arc::new(DirectoryHandles {
            file,
            _parent: parent,
            #[cfg(target_os = "linux")]
            containers,
            #[cfg(windows)]
            enumeration: std::sync::Mutex::new(()),
        })))
    }

    /// Pin an absolute root supplied by the settings or portal adapter. Its
    /// ancestors are part of that initial grant. The final entry must be a real
    /// directory, including when the input has a trailing separator or dot.
    pub fn open_root(path: &Path) -> io::Result<Self> {
        if !path.is_absolute()
            || path.components().any(|c| {
                c == Component::ParentDir
                    || matches!(c, Component::Normal(name) if internal_name(name))
            })
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "expected an absolute normalized watch root",
            ));
        }
        let root: PathBuf = path.components().collect();
        Self::from_file(native::open_root(&root)?, None)
    }

    pub fn open_directory(&self, name: &OsStr) -> io::Result<Self> {
        validate_child(name)?;
        Self::from_file(
            native::open_directory(&self.0.file, name)?,
            Some(self.clone()),
        )
    }

    fn file_lease(&self, name: &OsStr, writable_times: bool) -> io::Result<VerifiedFile> {
        validate_child(name)?;
        let file = native::open_file(&self.0.file, name, writable_times)?;
        let info = native::info(&file)?;
        info.require(EntryKind::File)?;
        Ok(VerifiedFile {
            file,
            identity: info.identity,
            parent: self.clone(),
            name: name.into(),
        })
    }

    /// Authorize a regular file for reading, hashing and metadata observations.
    pub fn open_file(&self, name: &OsStr) -> io::Result<VerifiedFile> {
        self.file_lease(name, false)
    }

    /// Acquire explicit timestamp-write authority over the selected file.
    pub fn open_for_time_repair(&self, name: &OsStr) -> io::Result<TimeRepairFile> {
        self.file_lease(name, true).map(TimeRepairFile)
    }

    /// Create a private stage for a single destination name. The destination
    /// is claimed atomically during publication.
    pub fn begin_download(&self, name: &OsStr) -> io::Result<Download> {
        validate_child(name)?;
        Download::new(self, name)
    }

    /// Enumerate immediate children under this same directory handle. A link,
    /// denied or disappearing entry, malformed result, or exceeded limit fails
    /// the entire call. The limit includes reserved names encountered on disk.
    pub fn entries(&self, limit: usize) -> io::Result<Vec<Entry>> {
        #[cfg(windows)]
        let _scan = self
            .0
            .enumeration
            .lock()
            .map_err(|_| io::Error::other("directory enumeration interrupted"))?;
        let mut entries = Vec::new();
        let mut remaining = limit;
        native::enumerate(&self.0.file, |name| {
            if name == "." || name == ".." {
                return Ok(());
            }
            remaining = remaining
                .checked_sub(1)
                .ok_or_else(|| io::Error::other("directory enumeration limit reached"))?;
            if internal_name(&name) {
                return Ok(());
            }
            validate_child(&name)?;
            let kind = native::entry_info(&self.0.file, &name)?.kind;
            entries.push(Entry { name, kind });
            Ok(())
        })?;
        Ok(entries)
    }
}

/// Data, identity and timestamps all refer to the same open file. Reads and
/// seeks never reopen the displayed name.
#[derive(Debug)]
pub struct VerifiedFile {
    file: File,
    identity: FileIdentity,
    parent: Directory,
    name: OsString,
}

impl VerifiedFile {
    pub fn metadata(&self) -> io::Result<Metadata> {
        self.file.metadata()
    }

    pub fn identity(&self) -> FileIdentity {
        self.identity
    }

    /// Missing or replaced entries cease to match. A lookup error such as a
    /// reparse point, denial or unsupported identity stays an error.
    pub fn is_current_entry(&self) -> io::Result<bool> {
        match native::entry_info(&self.parent.0.file, &self.name) {
            Ok(info) => Ok(info.kind == EntryKind::File && info.identity == self.identity),
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(false),
            Err(e) => Err(e),
        }
    }
}

impl Read for VerifiedFile {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        self.file.read(bytes)
    }
}

impl Seek for VerifiedFile {
    fn seek(&mut self, pos: SeekFrom) -> io::Result<u64> {
        self.file.seek(pos)
    }
}

#[derive(Debug)]
pub struct TimeRepairFile(VerifiedFile);

impl TimeRepairFile {
    /// Read/hash the selected file before committing a repair intent.
    pub fn media(&mut self) -> &mut VerifiedFile {
        &mut self.0
    }

    /// Apply times to the retained object after the caller verifies the digest
    /// and journals its intent. Linux supports updating mtime. Windows also
    /// updates creation time. Reject an observed alias or changed entry.
    pub fn set_times(&self, created: SystemTime, modified: SystemTime) -> io::Result<()> {
        if !self.0.is_current_entry()? || native::info(&self.0.file)?.links != 1 {
            return Err(denied(
                "timestamp repair requires the same single-link file",
            ));
        }
        let times = FileTimes::new().set_modified(modified);
        #[cfg(windows)]
        let times = std::os::windows::fs::FileTimesExt::set_created(times, created);
        #[cfg(target_os = "linux")]
        let _ = created;
        self.0.file.set_times(times)
    }
}
