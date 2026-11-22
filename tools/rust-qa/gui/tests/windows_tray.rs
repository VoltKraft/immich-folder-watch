#[path = "../src/windows_tray_state.rs"]
mod windows_tray_state;

use std::sync::mpsc::{TryRecvError, TrySendError, sync_channel};
use windows_tray_state::{Pending, TrayEvent};

#[test]
fn a_full_queue_preserves_availability_then_admits_one_coalesced_open() {
    let (sender, receiver) = sync_channel(1);
    let deliver = |event| sender.try_send(event);
    sender.send(TrayEvent::Open).unwrap();
    let mut pending = Pending {
        available: Some(false),
        open: Some(1),
    };
    assert_eq!(
        pending.flush(&deliver),
        Err(TrySendError::Full(TrayEvent::Availability(false)))
    );
    pending.open = Some(2);
    pending.available = Some(true);
    assert_eq!(receiver.recv().unwrap(), TrayEvent::Open);
    assert_eq!(
        pending.flush(&deliver),
        Err(TrySendError::Full(TrayEvent::Open))
    );
    assert_eq!(receiver.recv().unwrap(), TrayEvent::Availability(true));
    assert_eq!(pending.flush(&deliver), Ok(Some(2)));
    assert_eq!(pending.flush(&deliver), Ok(None));
    assert_eq!(receiver.recv().unwrap(), TrayEvent::Open);
    assert_eq!(receiver.try_recv(), Err(TryRecvError::Empty));
}

#[test]
fn a_disconnected_supervisor_cannot_acknowledge_the_pending_callback() {
    let (sender, receiver) = sync_channel(1);
    drop(receiver);
    let mut pending = Pending {
        available: None,
        open: Some(7),
    };
    assert_eq!(
        pending.flush(&|event| sender.try_send(event)),
        Err(TrySendError::Disconnected(TrayEvent::Open))
    );
    assert_eq!(pending.open, Some(7));
}
