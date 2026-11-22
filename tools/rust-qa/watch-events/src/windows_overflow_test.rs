use super::{ERROR_NOTIFY_ENUM_DIR, NotificationDirectory, ReadStage, Scope, Shared, prepare};
use crate::{Reason, Watch};
use std::collections::BTreeSet;
use std::fs::{self, File};
use std::io;
use std::os::windows::fs::OpenOptionsExt;
use std::path::Path;
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const FILES: u16 = 512;
const DEADLINE: Duration = Duration::from_secs(20);

fn open_directory(path: &Path, asynchronous: bool) -> io::Result<File> {
    File::options()
        .access_mode(0x10_0081)
        .share_mode(3)
        .custom_flags(0x0200_0000 | 0x0020_0000 | if asynchronous { 0x4000_0000 } else { 0 })
        .open(path)
}

fn filename(index: u16) -> String {
    format!("synthetic-notification-batch-watched-file-{index:04}.jpg")
}

fn inventory(watch: &Watch, path: &Path, expected: &BTreeSet<String>) -> io::Result<()> {
    let deadline = Instant::now() + DEADLINE;
    loop {
        let scan = watch.begin_inventory();
        let mut seen = BTreeSet::new();
        for entry in fs::read_dir(path)? {
            let entry = entry?;
            let name = entry.file_name().into_string().expect("ASCII fixture name");
            assert!(entry.file_type()?.is_file() && fs::read(entry.path())? == b"x");
            seen.insert(name);
        }
        assert_eq!(&seen, expected);
        if scan.finish(true) {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err(io::Error::other(
                "replacement watch inventory did not settle",
            ));
        }
    }
}

fn exercise(path: &Path) -> io::Result<()> {
    let grant = open_directory(path, false)?;
    let notification = || NotificationDirectory::bind(&grant, open_directory(path, true)?);
    let shared = Shared::new(1);
    let (stop, backend) = prepare(notification()?, Scope::Direct, &shared)?;
    let (ready, started) = mpsc::sync_channel(1);
    let (done, finished) = mpsc::channel();
    let (prime_bytes, loss_result) = thread::scope(|scope| -> io::Result<_> {
        let shared = &shared;
        let reader = scope.spawn(move || {
            let mut prime_bytes = 0;
            let mut loss = None;
            let outcome = backend.run_with_observer(shared, ready, |stage, result| {
                match (stage, result) {
                    (ReadStage::Completion, Ok(0)) => loss = Some("completion-zero-bytes"),
                    (ReadStage::Completion, Err(Some(ERROR_NOTIFY_ENUM_DIR))) => {
                        loss = Some("completion-error-1022");
                    }
                    (ReadStage::Submission, Err(Some(ERROR_NOTIFY_ENUM_DIR))) => {
                        loss = Some("submission-error-1022");
                    }
                    (ReadStage::Completion, Ok(n)) if prime_bytes == 0 => {
                        prime_bytes = n;
                        for index in 0..FILES {
                            fs::write(path.join(filename(index)), b"x")?;
                        }
                    }
                    _ => {}
                }
                Ok(())
            });
            let _ = done.send(());
            outcome.map(|()| (prime_bytes, loss))
        });
        let observation = (|| -> io::Result<()> {
            started.recv_timeout(DEADLINE).map_err(io::Error::other)?;
            fs::write(path.join("prime.jpg"), b"x")?;
            finished.recv_timeout(DEADLINE).map_err(io::Error::other)
        })();
        // Release any pending native read before joining, including on timeout.
        stop.signal()?;
        let result = reader.join().expect("native reader thread panicked")?;
        observation?;
        Ok(result)
    })?;
    assert!(prime_bytes > 0);
    let lost = shared.state.lock().unwrap().snapshot;
    assert!(lost.contains(Reason::NativeOverflow) && lost.requires_registration);
    assert!(lost.contains(Reason::QueueFull) && lost.peak_queued == 1);
    let source = loss_result.expect("missing native loss from the submitted or completed read");

    let mut replacement = Watch::start(notification()?, Scope::Direct, 1)?;
    let mut expected: BTreeSet<_> = (0..FILES).map(filename).collect();
    expected.insert("prime.jpg".into());
    inventory(&replacement, path, &expected)?;
    let before = replacement.snapshot();
    assert!(!before.requires_registration);
    fs::write(path.join("after.jpg"), b"x")?;
    let changed = replacement.wait_after(before.generation, DEADLINE);
    assert!(changed.generation > before.generation && changed.contains(Reason::Changed));
    expected.insert("after.jpg".into());
    inventory(&replacement, path, &expected)?;
    replacement.stop_and_join(DEADLINE)?;
    println!(
        "NATIVE_WATCH_OVERFLOW {source} {prime_bytes} {FILES} {} {} {} {} {}",
        lost.generation,
        lost.reasons,
        u8::from(lost.requires_registration),
        lost.peak_queued,
        expected.len()
    );
    Ok(())
}

#[test]
fn native_buffer_loss_retires_the_watch_and_a_fresh_watch_recovers() {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!("ifw-watch-loss-{}-{stamp}", std::process::id()));
    fs::create_dir(&path).unwrap();
    let result = std::panic::catch_unwind(|| exercise(&path));
    fs::remove_dir_all(path).unwrap();
    result.unwrap().unwrap();
}
