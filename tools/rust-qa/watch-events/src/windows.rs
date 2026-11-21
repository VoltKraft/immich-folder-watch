use super::windows_status::{self, ERROR_NOTIFY_ENUM_DIR, Next};
use super::{Scope, Shared};
use std::ffi::c_void;
use std::fs::File;
use std::io;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle, RawHandle};
use std::ptr::{null, null_mut};
use std::sync::Arc;
use std::sync::mpsc::SyncSender;

const FILE_LIST_DIRECTORY: u32 = 1;
const SHARE_READ_WRITE_DELETE: u32 = 7;
const BACKUP_SEMANTICS: u32 = 0x0200_0000;
const OVERLAPPED_IO: u32 = 0x4000_0000;
// File name, directory name, size, last write and creation time.
const CHANGES: u32 = 1 | 2 | 8 | 0x10 | 0x40;
const ERROR_OPERATION_ABORTED: i32 = 995;
const ERROR_NOT_FOUND: i32 = 1168;

#[repr(C)]
struct Overlapped {
    internal: usize,
    internal_high: usize,
    offsets: [u32; 2],
    event: RawHandle,
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn ReOpenFile(original: RawHandle, access: u32, share: u32, flags: u32) -> RawHandle;
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

fn event() -> io::Result<OwnedHandle> {
    // SAFETY: this creates an unnamed, non-inheritable, manual-reset event.
    let handle = unsafe { CreateEventW(null(), 1, 0, null()) };
    if handle.is_null() {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: CreateEventW returned a new owned handle.
    Ok(unsafe { OwnedHandle::from_raw_handle(handle) })
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

pub(super) fn prepare(
    directory: &File,
    scope: Scope<'_>,
    _: &Shared,
) -> io::Result<(Stop, Backend)> {
    // SAFETY: reopen the caller's live directory object for asynchronous notification.
    let raw = unsafe {
        ReOpenFile(
            directory.as_raw_handle(),
            FILE_LIST_DIRECTORY,
            SHARE_READ_WRITE_DELETE,
            BACKUP_SEMANTICS | OVERLAPPED_IO,
        )
    };
    if raw as isize == -1 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: ReOpenFile succeeded and returned an independently owned handle.
    let directory = unsafe { OwnedHandle::from_raw_handle(raw) };
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
        let mut ready = Some(ready);
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
            if windows_status::submitted(error, shared)? == Next::ReplaceAfterInventory {
                // No I/O was submitted. Expose overflow even on the very first arm.
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
                    if windows_status::completed(self.completion(pending), shared)?
                        == Next::ReplaceAfterInventory
                    {
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
mod tests {
    use super::*;

    #[test]
    fn native_request_has_the_64_bit_windows_abi() {
        assert_eq!(size_of::<Overlapped>(), 32);
        assert_eq!(std::mem::offset_of!(Overlapped, event), 24);
    }
}
