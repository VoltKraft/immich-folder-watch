//! Admission of one local show request to the bounded native GUI command queue.
use std::io;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::TrySendError;
use std::thread;
use std::time::Duration;

/// Old PID-only fixture records still allow ordinary activation without a foreground handoff.
pub(crate) fn primary_identity(text: &str) -> io::Result<(u32, Option<u64>)> {
    let (pid, created) = text
        .split_once(' ')
        .map_or((text, None), |(pid, stamp)| (pid, Some(stamp)));
    let pid = pid.parse::<u32>().map_err(io::Error::other)?;
    if matches!(pid, 0 | u32::MAX) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid primary PID",
        ));
    }
    let created = created
        .map(str::parse::<u64>)
        .transpose()
        .map_err(io::Error::other)?;
    if created == Some(0) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid primary creation time",
        ));
    }
    Ok((pid, created))
}

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
