#[path = "../src/launcher_delivery.rs"]
mod launcher_delivery;

use launcher_delivery::enqueue;
use std::io;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{TryRecvError, TrySendError, sync_channel};
use std::thread;
use std::time::Duration;

#[test]
fn primary_identity_accepts_old_pid_records_and_rejects_unusable_grant_targets() {
    assert_eq!(
        launcher_delivery::primary_identity("34").unwrap(),
        (34, None)
    );
    assert_eq!(
        launcher_delivery::primary_identity("34 122").unwrap(),
        (34, Some(122))
    );
    for invalid in [
        "0",
        "4294967295",
        "2 0",
        "3 ",
        "12 44 trailing",
        "0 4",
        "xyz",
    ] {
        assert!(
            launcher_delivery::primary_identity(invalid).is_err(),
            "{invalid}"
        );
    }
}

#[test]
fn full_queue_delivers_exactly_one_activation_after_the_first_slot_opens() {
    let (sender, receiver) = sync_channel(8);
    for command in 0..8 {
        sender.send(command).unwrap();
    }
    let (full, observed_full) = sync_channel(1);
    let (finished, delivery) = sync_channel(1);
    let worker = thread::spawn(move || {
        let queued = enqueue(&AtomicBool::new(false), || {
            let result = sender.try_send(8);
            if matches!(result, Err(TrySendError::Full(_))) {
                let _ = full.try_send(());
            }
            result
        });
        finished.send(queued).unwrap();
    });
    observed_full.recv_timeout(Duration::from_secs(2)).unwrap();
    assert_eq!(receiver.recv().unwrap(), 0);
    assert!(
        delivery
            .recv_timeout(Duration::from_secs(2))
            .unwrap()
            .unwrap()
    );
    worker.join().unwrap();
    assert_eq!(
        receiver.into_iter().collect::<Vec<_>>(),
        (1..=8).collect::<Vec<_>>()
    );
}

#[test]
fn shutdown_interrupts_a_pending_activation_and_preserves_the_queued_command() {
    let (sender, receiver) = sync_channel(1);
    sender.send("quit").unwrap();
    let (full, observed_full) = sync_channel(1);
    let stopping = Arc::new(AtomicBool::new(false));
    let shutdown = Arc::clone(&stopping);
    let (finished, delivery) = sync_channel(1);
    let worker = thread::spawn(move || {
        let queued = enqueue(&shutdown, || {
            let result = sender.try_send("open");
            if matches!(result, Err(TrySendError::Full(_))) {
                let _ = full.try_send(());
            }
            result
        });
        finished.send(queued).unwrap();
    });
    observed_full.recv_timeout(Duration::from_secs(2)).unwrap();
    stopping.store(true, Ordering::Release);
    worker.thread().unpark();
    assert!(
        !delivery
            .recv_timeout(Duration::from_secs(2))
            .unwrap()
            .unwrap()
    );
    worker.join().unwrap();
    assert_eq!(receiver.recv().unwrap(), "quit");
    assert_eq!(receiver.try_recv(), Err(TryRecvError::Disconnected));
}

#[test]
fn closed_receiver_reports_a_delivery_failure() {
    let (sender, receiver) = sync_channel(1);
    drop(receiver);
    let error = enqueue(&AtomicBool::new(false), || sender.try_send(())).unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::BrokenPipe);
}
