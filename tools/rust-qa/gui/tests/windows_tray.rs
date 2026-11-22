#[path = "../src/windows_tray_state.rs"]
mod windows_tray_state;

use std::sync::mpsc::{TryRecvError, TrySendError, sync_channel};
use std::time::{Duration, Instant};
use windows_tray_state::{Attempt, Pending, Recovery, TrayEvent};

#[test]
fn a_replacement_can_refuse_twice_before_acknowledging_and_cancelling_retries() {
    let old = Some((12, 40));
    let new = Some((13, 41));
    let now = Instant::now();
    let at = |s| now + Duration::from_secs(s);
    let mut recovery = Recovery::new(old);
    recovery.result(true, at(0));
    assert_eq!(recovery.observe(new, false, at(1)), Some(Attempt::Recreate));
    recovery.result(false, at(1));
    assert_eq!(recovery.observe(new, false, at(3)), None);
    assert_eq!(recovery.observe(new, false, at(4)), Some(Attempt::Retry));
    recovery.result(false, at(4));
    assert_eq!(recovery.observe(new, false, at(9)), None);
    assert_eq!(recovery.observe(new, false, at(10)), Some(Attempt::Retry));
    recovery.result(true, at(10));
    assert_eq!(recovery.observe(new, false, at(150)), None);
}

#[test]
fn continued_refusals_back_off_to_one_attempt_every_thirty_seconds() {
    let host = Some((23, 50));
    let mut now = Instant::now();
    let mut recovery = Recovery::new(host);
    for delay in [3, 6, 12, 24, 30, 30, 30] {
        recovery.result(false, now);
        now += Duration::from_secs(delay);
        assert_eq!(
            recovery.observe(host, false, now - Duration::from_secs(1)),
            None
        );
        assert_eq!(recovery.observe(host, false, now), Some(Attempt::Retry));
        assert_eq!(recovery.observe(host, false, now), None);
    }
}

#[test]
fn absence_cancels_a_pending_retry_and_only_a_live_host_can_restart_it() {
    let first = Some((17, 91));
    let second = Some((18, 91)); // The same process can recreate its top-level host.
    let now = Instant::now();
    let at = |s| now + Duration::from_secs(s);
    let mut recovery = Recovery::new(first);
    recovery.result(false, at(0));
    assert_eq!(
        recovery.observe(second, false, at(1)),
        Some(Attempt::Recreate)
    );
    recovery.result(false, at(1));
    assert_eq!(recovery.observe(second, false, at(3)), None);
    assert_eq!(recovery.observe(second, false, at(4)), Some(Attempt::Retry));
    recovery.result(false, at(4));
    assert_eq!(recovery.observe(None, false, at(6)), None);
    recovery.result(false, at(6));
    assert_eq!(recovery.observe(None, true, at(8)), None);
    assert_eq!(recovery.observe(None, false, at(90)), None);
    assert_eq!(
        recovery.observe(second, false, at(91)),
        Some(Attempt::Recreate)
    );
    recovery.result(false, at(91));
    assert_eq!(
        recovery.observe(second, false, at(94)),
        Some(Attempt::Retry)
    );
    recovery.result(false, at(94));
    assert_eq!(
        recovery.observe(second, true, at(95)),
        Some(Attempt::Recreate)
    );
    recovery.result(false, at(95));
    assert_eq!(
        recovery.observe(second, false, at(98)),
        Some(Attempt::Retry)
    );
}

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
