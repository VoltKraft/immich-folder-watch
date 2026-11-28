use super::windows_status::{self, ERROR_NOTIFY_ENUM_DIR, Next};
use super::{Scope, Shared};
use std::ffi::c_void;
use std::fmt::Write as _;
use std::fs::File;
use std::io;
use std::os::windows::fs::MetadataExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle, RawHandle};
use std::ptr::{null, null_mut};
use std::sync::Arc;
use std::sync::mpsc::SyncSender;

const FILE_LIST_DIRECTORY: u32 = 1;
const FILE_READ_ATTRIBUTES: u32 = 0x80;
const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
const SYNCHRONOUS_IO: u32 = 0x10 | 0x20;
// File name, directory name, size, last write and creation time.
const CHANGES: u32 = 1 | 2 | 8 | 0x10 | 0x40;
const ERROR_OPERATION_ABORTED: i32 = 995;
const ERROR_NOT_FOUND: i32 = 1168;

pub(super) fn observed<T>(operation: &str, result: io::Result<T>) -> io::Result<T> {
    if let Err(error) = &result
        && std::env::var_os("IFW_WATCH_DIAGNOSTICS").as_deref() == Some(std::ffi::OsStr::new("1"))
    {
        eprintln!("WATCH_OPERATION {operation} {error}");
    }
    result
}

#[repr(C)]
struct Overlapped {
    internal: usize,
    internal_high: usize,
    offsets: [u32; 2],
    event: RawHandle,
}

#[repr(C)]
#[derive(Default, PartialEq, Eq)]
struct FileIdInfo {
    volume: u64,
    file_id: [u8; 16],
}

#[repr(C)]
#[derive(Default)]
struct IoStatusBlock {
    status: usize,
    information: usize,
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetFileInformationByHandleEx(
        file: RawHandle,
        class: i32,
        information: *mut c_void,
        size: u32,
    ) -> i32;
    fn CreateEventW(
        security: *const c_void,
        manual: i32,
        initial: i32,
        name: *const u16,
    ) -> RawHandle;
    fn SetEvent(event: RawHandle) -> i32;
    fn ResetEvent(event: RawHandle) -> i32;
    fn WaitForMultipleObjects(count: u32, handles: *const RawHandle, all: i32, millis: u32) -> u32;
    fn ReadDirectoryChangesW(
        directory: RawHandle,
        buffer: *mut c_void,
        bytes: u32,
        subtree: i32,
        filter: u32,
        count: *mut u32,
        overlapped: *mut Overlapped,
        completion: *const c_void,
    ) -> i32;
    fn GetOverlappedResult(
        directory: RawHandle,
        overlapped: *mut Overlapped,
        count: *mut u32,
        wait: i32,
    ) -> i32;
    fn CancelIoEx(directory: RawHandle, overlapped: *mut Overlapped) -> i32;
}

#[link(name = "ntdll")]
unsafe extern "system" {
    fn NtQueryInformationFile(
        file: RawHandle,
        status: *mut IoStatusBlock,
        information: *mut c_void,
        length: u32,
        class: i32,
    ) -> i32;
    fn RtlNtStatusToDosError(status: i32) -> u32;
}

fn information_u32(file: &File, class: i32) -> io::Result<u32> {
    let mut status = IoStatusBlock::default();
    let mut value = 0u32;
    // SAFETY: access/mode queries are synchronous APIs even on asynchronous
    // file objects. Both writable buffers cover their declared native layouts.
    let result = unsafe {
        NtQueryInformationFile(
            file.as_raw_handle(),
            &raw mut status,
            (&raw mut value).cast(),
            size_of_val(&value) as u32,
            class,
        )
    };
    if result < 0 {
        // SAFETY: this converts the returned NTSTATUS without dereferencing memory.
        return Err(io::Error::from_raw_os_error(
            unsafe { RtlNtStatusToDosError(result) } as i32,
        ));
    }
    if status.information != size_of_val(&value) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "incomplete notification handle information",
        ));
    }
    Ok(value)
}

/// A dedicated asynchronous file object acquired inside the caller's authorized
/// directory grant. Acquisition must deny delete sharing and open the entry
/// without following reparse points. The file must have no other outstanding I/O.
///
/// Binding verifies the expected directory; it does not authorize a pathname or
/// confer permission for file mutations. Acquire distinct file objects for
/// simultaneous or replacement subscriptions, never `try_clone` an active watch.
pub struct NotificationDirectory(File);

impl NotificationDirectory {
    pub fn bind(authorized: &File, notification: File) -> io::Result<Self> {
        let attributes = notification.metadata()?;
        if !attributes.is_dir()
            || attributes.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
            || identity(authorized)? != identity(&notification)?
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "notification acquisition differs from the authorized directory",
            ));
        }
        let access = observed(
            "notification FileAccessInformation",
            information_u32(&notification, 8),
        )?;
        let mode = observed(
            "notification FileModeInformation",
            information_u32(&notification, 16),
        )?;
        if access & (FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES)
            != FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES
            || mode & SYNCHRONOUS_IO != 0
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "notification acquisition requires an asynchronous listing handle",
            ));
        }
        Ok(Self(notification))
    }

    pub(super) fn file(&self) -> &File {
        &self.0
    }
}

fn identity(handle: &impl AsRawHandle) -> io::Result<FileIdInfo> {
    let mut id = FileIdInfo::default();
    // SAFETY: the caller owns a live handle and the output covers one FILE_ID_INFO.
    let ok = unsafe {
        GetFileInformationByHandleEx(
            handle.as_raw_handle(),
            18, // FileIdInfo
            (&raw mut id).cast(),
            size_of::<FileIdInfo>() as u32,
        )
    };
    if ok == 0 {
        return observed(
            "GetFileInformationByHandleEx",
            Err(io::Error::last_os_error()),
        );
    }
    observed(
        "FileIdInfo identity support",
        windows_status::require_file_id(&id.file_id),
    )?;
    Ok(id)
}

fn event() -> io::Result<OwnedHandle> {
    // SAFETY: this creates an unnamed, non-inheritable, manual-reset event.
    let handle = unsafe { CreateEventW(null(), 1, 0, null()) };
    if handle.is_null() {
        return observed("CreateEventW", Err(io::Error::last_os_error()));
    }
    // SAFETY: CreateEventW returned a new owned handle.
    Ok(unsafe { OwnedHandle::from_raw_handle(handle) })
}

fn trace_notification(buffer: &[u32], count: u32, generation: u64, traced: &mut usize) {
    // Fixture-only diagnostics: preserve the actual completed bytes without
    // filtering wakeups. At most 32 native buffers are emitted per flat watch.
    if *traced == 32 {
        eprintln!("WATCH_NOTIFY_TRUNCATED");
        *traced += 1;
        return;
    }
    if *traced > 32 {
        return;
    }
    *traced += 1;
    if count as usize > size_of_val(buffer) {
        eprintln!("WATCH_NOTIFY_INVALID_COUNT {count}");
        return;
    }
    let mut line = format!("WATCH_NOTIFY {generation} {count} ");
    for byte in buffer
        .iter()
        .flat_map(|word| word.to_ne_bytes())
        .take(count as usize)
    {
        let _ = write!(line, "{byte:02x}");
    }
    eprintln!("{line}");
}

pub(super) struct Stop(Arc<OwnedHandle>);

impl Stop {
    pub(super) fn signal(&self) -> io::Result<()> {
        // SAFETY: the shared event stays live until after the worker has drained.
        if unsafe { SetEvent(self.0.as_raw_handle()) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }
}

pub(super) struct Backend {
    directory: OwnedHandle,
    stop: Arc<OwnedHandle>,
    completed: OwnedHandle,
    tree: bool,
}

#[derive(Clone, Copy)]
enum ReadStage {
    Submission,
    Completion,
}

pub(super) fn prepare(
    directory: NotificationDirectory,
    scope: Scope<'_>,
    _: &Shared,
) -> io::Result<(Stop, Backend)> {
    // Move the acquired object, including its original open mode and sharing
    // lease. An ID lookup can identify the same directory while producing a
    // file object that the filesystem refuses for directory notifications.
    let directory: OwnedHandle = directory.0.into();
    let stop = Arc::new(event()?);
    let tree = matches!(scope, Scope::Tree { .. });
    Ok((
        Stop(Arc::clone(&stop)),
        Backend {
            directory,
            stop,
            completed: event()?,
            tree,
        },
    ))
}

impl Backend {
    fn completion(&self, request: *mut Overlapped) -> io::Result<u32> {
        let mut count = 0;
        // SAFETY: exactly this request is outstanding on this handle. The
        // caller retains its buffer and OVERLAPPED storage throughout this wait.
        if unsafe { GetOverlappedResult(self.directory.as_raw_handle(), request, &mut count, 1) }
            == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(count)
    }

    fn cancel_and_drain(&self, request: *mut Overlapped) -> io::Result<()> {
        // SAFETY: this addresses only the outstanding request owned by this worker.
        let cancellation = if unsafe { CancelIoEx(self.directory.as_raw_handle(), request) } == 0 {
            let error = io::Error::last_os_error();
            (error.raw_os_error() != Some(ERROR_NOT_FOUND)).then_some(error)
        } else {
            None
        };
        // A racing completion is valid. Cancellation alone never releases the storage.
        let finished = self.completion(request);
        if let Some(error) = cancellation {
            return Err(error);
        }
        match finished {
            Ok(_) => Ok(()),
            Err(e)
                if e.raw_os_error() == Some(ERROR_OPERATION_ABORTED)
                    || e.raw_os_error() == Some(ERROR_NOTIFY_ENUM_DIR) =>
            {
                Ok(())
            }
            Err(e) => Err(e),
        }
    }

    pub(super) fn run(self, shared: &Shared, ready: SyncSender<()>) -> io::Result<()> {
        self.run_with_observer(shared, ready, |_, _| Ok(()))
    }

    fn run_with_observer(
        self,
        shared: &Shared,
        ready: SyncSender<()>,
        mut observe: impl FnMut(ReadStage, Result<u32, Option<i32>>) -> io::Result<()>,
    ) -> io::Result<()> {
        let mut ready = Some(ready);
        let trace = !self.tree
            && std::env::var_os("IFW_WATCH_DIAGNOSTICS").as_deref()
                == Some(std::ffi::OsStr::new("1"));
        let mut traced = 0;
        // DWORD alignment and a 32-KiB buffer also satisfy the documented remote limit.
        let mut buffer = [0u32; 8192];
        let handles = [self.stop.as_raw_handle(), self.completed.as_raw_handle()];
        loop {
            // SAFETY: the previous request has completed before this event is reused.
            if unsafe { ResetEvent(handles[1]) } == 0 {
                return Err(io::Error::last_os_error());
            }
            let mut request = Overlapped {
                internal: 0,
                internal_high: 0,
                offsets: [0; 2],
                event: handles[1],
            };
            let pending = &raw mut request;
            // SAFETY: the aligned buffer and OVERLAPPED remain in this scope,
            // unmoved and exclusively accessible to the OS until completion.
            let started = unsafe {
                ReadDirectoryChangesW(
                    self.directory.as_raw_handle(),
                    buffer.as_mut_ptr().cast(),
                    size_of_val(&buffer) as u32,
                    i32::from(self.tree),
                    CHANGES,
                    null_mut(),
                    pending,
                    null(),
                )
            };
            let error = (started == 0).then(io::Error::last_os_error);
            let code = error.as_ref().and_then(io::Error::raw_os_error);
            if observed(
                "ReadDirectoryChangesW",
                windows_status::submitted(error, shared),
            )? == Next::ReplaceAfterInventory
            {
                // No I/O was submitted. Expose overflow even on the very first arm.
                observe(ReadStage::Submission, Err(code))?;
                if let Some(announce) = ready.take() {
                    let _ = announce.send(());
                }
                return Ok(());
            }
            if let Some(announce) = ready.take()
                && announce.send(()).is_err()
            {
                return self.cancel_and_drain(pending);
            }
            // SAFETY: both distinct unnamed events stay open for the whole wait.
            let signaled = unsafe { WaitForMultipleObjects(2, handles.as_ptr(), 0, u32::MAX) };
            match signaled {
                0 => return self.cancel_and_drain(pending),
                1 => {
                    let completed = self.completion(pending);
                    // No request is outstanding here. The native test adds an ordinary
                    // batch of files between reads on this same directory handle.
                    observe(
                        ReadStage::Completion,
                        completed.as_ref().copied().map_err(io::Error::raw_os_error),
                    )?;
                    let count = completed.as_ref().ok().copied();
                    let next = windows_status::completed(completed, shared)?;
                    if trace && let Some(count) = count {
                        let generation = shared.state.lock().unwrap().snapshot.generation;
                        trace_notification(&buffer, count, generation, &mut traced);
                    }
                    if next == Next::ReplaceAfterInventory {
                        return Ok(());
                    }
                }
                _ => {
                    let wait_error = io::Error::last_os_error();
                    self.cancel_and_drain(pending)?;
                    return Err(wait_error);
                }
            }
        }
    }
}

#[cfg(test)]
#[path = "windows_overflow_test.rs"]
mod overflow_test;

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::windows::fs::OpenOptionsExt;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn native_request_has_the_64_bit_windows_abi() {
        assert_eq!(size_of::<Overlapped>(), 32);
        assert_eq!(std::mem::offset_of!(Overlapped, event), 24);
        assert_eq!(size_of::<FileIdInfo>(), 24);
        assert_eq!(std::mem::offset_of!(FileIdInfo, file_id), 8);
        assert_eq!(size_of::<IoStatusBlock>(), 16);
        assert_eq!(std::mem::offset_of!(IoStatusBlock, information), 8);
    }

    #[test]
    fn binding_accepts_only_the_matching_asynchronous_directory() {
        let name = format!(
            "ifw-watch-bind-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        let path = std::env::temp_dir().join(name);
        std::fs::create_dir(&path).unwrap();
        std::fs::create_dir(path.join("other")).unwrap();
        let open = |path: &std::path::Path, asynchronous| {
            File::options()
                .access_mode(FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | 0x10_0000)
                .share_mode(3)
                .custom_flags(0x0200_0000 | 0x20_0000 | if asynchronous { 0x4000_0000 } else { 0 })
                .open(path)
                .unwrap()
        };
        {
            let authorized = open(&path, false);
            assert!(NotificationDirectory::bind(&authorized, open(&path, false)).is_err());
            assert!(
                NotificationDirectory::bind(&authorized, open(&path.join("other"), true)).is_err()
            );
            let without_listing = File::options()
                .access_mode(FILE_READ_ATTRIBUTES | 0x10_0000)
                .share_mode(3)
                .custom_flags(0x0200_0000 | 0x20_0000 | 0x4000_0000)
                .open(&path)
                .unwrap();
            assert!(NotificationDirectory::bind(&authorized, without_listing).is_err());
            let notification = NotificationDirectory::bind(&authorized, open(&path, true)).unwrap();
            drop(notification);
        }
        std::fs::remove_dir_all(path).unwrap();
    }
}
