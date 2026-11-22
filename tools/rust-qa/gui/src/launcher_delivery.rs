//! Admission of one local show request to the bounded native GUI command queue.
use std::io;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::TrySendError;
use std::thread;
use std::time::Duration;

/// The pipe listener retains this request while the UI is busy. Shutdown unparks the listener.
pub(crate) fn enqueue<T>(
    stopping: &AtomicBool,
    try_open: impl Fn() -> Result<(), TrySendError<T>>,
) -> io::Result<bool> {
    while !stopping.load(Ordering::Acquire) {
        match try_open() {
            Ok(()) => return Ok(true),
            Err(TrySendError::Full(_)) => thread::park_timeout(Duration::from_millis(5)),
            Err(TrySendError::Disconnected(_)) => {
                return Err(io::Error::new(
                    io::ErrorKind::BrokenPipe,
                    "the local activation receiver closed",
                ));
            }
        }
    }
    Ok(false)
}
