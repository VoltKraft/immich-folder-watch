//! ReadDirectoryChangesW submission and completion decisions.

use super::{Reason, Shared};
use std::io;

const ERROR_IO_PENDING: i32 = 997;
pub(super) const ERROR_NOTIFY_ENUM_DIR: i32 = 1022;

#[derive(Debug, PartialEq, Eq)]
pub(super) enum Next {
    Continue,
    ReplaceAfterInventory,
}

fn overflow(shared: &Shared) -> Next {
    shared.record(Reason::NativeOverflow);
    Next::ReplaceAfterInventory
}

pub(super) fn submitted(error: Option<io::Error>, shared: &Shared) -> io::Result<Next> {
    match error {
        None => Ok(Next::Continue),
        Some(e) if e.raw_os_error() == Some(ERROR_IO_PENDING) => Ok(Next::Continue),
        Some(e) if e.raw_os_error() == Some(ERROR_NOTIFY_ENUM_DIR) => Ok(overflow(shared)),
        Some(e) => Err(e),
    }
}

pub(super) fn completed(result: io::Result<u32>, shared: &Shared) -> io::Result<Next> {
    match result {
        Ok(0) => Ok(overflow(shared)),
        Err(e) if e.raw_os_error() == Some(ERROR_NOTIFY_ENUM_DIR) => Ok(overflow(shared)),
        Ok(_) => {
            shared.record(Reason::Changed);
            Ok(Next::Continue)
        }
        Err(e) => Err(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn immediate_enumeration_error_retires_the_registration_without_a_retry() {
        let state = Shared::new(1);
        state.record(Reason::Changed);
        assert_eq!(
            submitted(
                Some(io::Error::from_raw_os_error(ERROR_NOTIFY_ENUM_DIR)),
                &state
            )
            .unwrap(),
            Next::ReplaceAfterInventory
        );
        let snapshot = state.state.lock().unwrap().snapshot;
        assert!(snapshot.contains(Reason::NativeOverflow) && snapshot.requires_registration);
        assert!(snapshot.contains(Reason::QueueFull));
        assert_eq!(snapshot.queued, 1);
        assert_eq!(submitted(None, &state).unwrap(), Next::Continue);
        assert_eq!(
            submitted(Some(io::Error::from_raw_os_error(ERROR_IO_PENDING)), &state).unwrap(),
            Next::Continue
        );
        assert!(submitted(Some(io::Error::from_raw_os_error(5)), &state).is_err());
    }

    #[test]
    fn zero_bytes_and_enumeration_error_on_completion_each_retire_the_request() {
        for result in [
            Ok(0),
            Err(io::Error::from_raw_os_error(ERROR_NOTIFY_ENUM_DIR)),
        ] {
            let state = Shared::new(1);
            assert_eq!(
                completed(result, &state).unwrap(),
                Next::ReplaceAfterInventory
            );
            let snapshot = state.state.lock().unwrap().snapshot;
            assert!(snapshot.contains(Reason::NativeOverflow) && snapshot.requires_registration);
        }
        let state = Shared::new(1);
        assert_eq!(completed(Ok(12), &state).unwrap(), Next::Continue);
        assert!(
            state
                .state
                .lock()
                .unwrap()
                .snapshot
                .contains(Reason::Changed)
        );
        assert!(completed(Err(io::Error::from_raw_os_error(5)), &state).is_err());
    }
}
