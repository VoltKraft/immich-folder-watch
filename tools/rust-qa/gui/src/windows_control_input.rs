//! Shut down the fixture's dedicated Windows pipe reader while its external writer is still open.
use std::fs::File;
use std::io::{self, Read};
use std::os::windows::io::{AsHandle, AsRawHandle, RawHandle};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

#[link(name = "kernel32")]
unsafe extern "system" {
    fn CancelSynchronousIo(thread: RawHandle) -> i32;
}

pub struct Input {
    file: File,
    stopping: Arc<AtomicBool>,
}

impl Input {
    /// Read the bootstrap and subsequent bytes from the same unbuffered pipe handle.
    pub fn stdin() -> io::Result<Self> {
        Self::from_handle(io::stdin())
    }

    fn from_handle(handle: impl AsHandle) -> io::Result<Self> {
        Ok(Self {
            file: File::from(handle.as_handle().try_clone_to_owned()?),
            stopping: Arc::default(),
        })
    }

    pub fn read_byte(&mut self) -> io::Result<u8> {
        if self.stopping.load(Ordering::Acquire) {
            return Err(io::ErrorKind::Interrupted.into());
        }
        let mut byte = [0];
        let count = self.file.read(&mut byte)?;
        if self.stopping.load(Ordering::Acquire) {
            return Err(io::ErrorKind::Interrupted.into());
        }
        if count == 0 {
            return Err(io::ErrorKind::UnexpectedEof.into());
        }
        Ok(byte[0])
    }

    pub fn listen(self, run: impl FnOnce(Self) + Send + 'static) -> io::Result<ControlReader> {
        let stopping = Arc::clone(&self.stopping);
        let reader = thread::Builder::new()
            .name("windows-control-input".into())
            .spawn(move || run(self))?;
        Ok(ControlReader { stopping, reader })
    }
}

pub struct ControlReader {
    stopping: Arc<AtomicBool>,
    reader: JoinHandle<()>,
}

impl ControlReader {
    /// Call after disconnecting command receivers, including senders under backpressure.
    pub fn stop(self) -> io::Result<()> {
        self.stopping.store(true, Ordering::Release);
        let deadline = Instant::now() + Duration::from_secs(3);
        while !self.reader.is_finished() {
            // The join handle owns this dedicated thread throughout cancellation. ERROR_NOT_FOUND
            // also occurs in the gap between its last flag check and entering synchronous ReadFile.
            if unsafe { CancelSynchronousIo(self.reader.as_raw_handle()) } == 0 {
                let error = io::Error::last_os_error();
                if error.raw_os_error() != Some(1168) && !self.reader.is_finished() {
                    return Err(error);
                }
            }
            if Instant::now() >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Control input did not exit",
                ));
            }
            thread::sleep(Duration::from_millis(10));
        }
        self.reader
            .join()
            .map_err(|_| io::Error::other("Control input panicked"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::os::windows::io::{FromRawHandle, OwnedHandle};
    use std::ptr::{null, null_mut};
    use std::sync::mpsc;

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn CreatePipe(
            read: *mut RawHandle,
            write: *mut RawHandle,
            security: *const (),
            size: u32,
        ) -> i32;
    }

    #[test]
    fn reader_stops_with_the_original_pipe_writer_open() -> io::Result<()> {
        let (mut read, mut write) = (null_mut(), null_mut());
        // Match the launcher's synchronous anonymous pipe and take both newly owned handles.
        if unsafe { CreatePipe(&mut read, &mut write, null(), 0) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let (read, mut write) = unsafe {
            (
                OwnedHandle::from_raw_handle(read),
                File::from_raw_handle(write),
            )
        };
        let input = Input::from_handle(read)?;
        let (started, observed) = mpsc::sync_channel(1);
        let reader = input.listen(move |mut input| {
            started.send(input.read_byte().unwrap()).unwrap();
            assert!(input.read_byte().is_err());
        })?;
        write.write_all(b"B")?;
        assert_eq!(observed.recv_timeout(Duration::from_secs(2)), Ok(b'B'));
        reader.stop()?;
        assert!(write.write_all(b"Q").is_err());
        Ok(())
    }
}
