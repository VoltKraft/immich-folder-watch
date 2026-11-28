//! Own the optional Linux comparison worker for this development fixture.
use std::io;
use std::process::{Child, Command, Stdio};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, SyncSender, TrySendError};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

#[derive(Clone)]
pub(super) struct Restarts {
    wake: SyncSender<()>,
    closing: Arc<AtomicBool>,
}

impl Restarts {
    pub(super) fn begin_quit(&self) {
        self.closing.store(true, Ordering::Release);
        // A full channel already wakes the owner. Other senders can outlive Quit.
        let _ = self.wake.try_send(());
    }

    pub(super) fn request(&self) {
        if !self.closing.load(Ordering::Acquire) {
            match self.wake.try_send(()) {
                Ok(()) => {}
                Err(TrySendError::Full(())) => println!("WORKER_RESTART_PENDING"),
                Err(TrySendError::Disconnected(())) => {
                    eprintln!("WORKER_RESTART_FAILED owner disconnected");
                }
            }
        }
    }
}

pub(super) struct Benchmark(Option<(Restarts, JoinHandle<io::Result<()>>)>);

impl Benchmark {
    pub(super) fn start() -> io::Result<Self> {
        if std::env::var("IFW_QA_BENCHMARK").as_deref() != Ok("1") {
            return Ok(Self(None));
        }
        Self::start_program(Command::new("/app/ifw-performance-worker"))
    }

    fn start_program(command: Command) -> io::Result<Self> {
        let mut worker = Worker {
            command,
            child: None,
        };
        worker.spawn()?;
        let (wake, events) = mpsc::sync_channel(1);
        let closing = Arc::new(AtomicBool::new(false));
        let stop = Arc::clone(&closing);
        let thread = thread::Builder::new()
            .name("linux-inventory-owner".into())
            .spawn(move || {
                while events.recv().is_ok() && !stop.load(Ordering::Acquire) {
                    if let Err(error) = worker.restart(&stop) {
                        eprintln!("WORKER_RESTART_FAILED {error}");
                        if stop.load(Ordering::Acquire) {
                            return Err(error);
                        }
                    }
                }
                worker.stop("quit").map(|_| ())
            })?;
        Ok(Self(Some((Restarts { wake, closing }, thread))))
    }

    pub(super) fn restarts(&self) -> Option<Restarts> {
        self.0.as_ref().map(|(requests, _)| requests.clone())
    }

    pub(super) fn finish(mut self) -> io::Result<()> {
        self.shutdown()
    }

    fn shutdown(&mut self) -> io::Result<()> {
        if let Some((requests, thread)) = self.0.take() {
            requests.begin_quit();
            thread
                .join()
                .map_err(|_| io::Error::other("Inventory owner panicked"))??;
        }
        Ok(())
    }
}

impl Drop for Benchmark {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}

struct Worker {
    command: Command,
    child: Option<Child>,
}

impl Worker {
    fn spawn(&mut self) -> io::Result<u32> {
        if self.child.is_some() {
            return Err(io::Error::other(
                "Previous inventory process is still owned",
            ));
        }
        let child = self.command.stdin(Stdio::piped()).spawn()?;
        let pid = child.id();
        self.child = Some(child);
        println!("INVENTORY_WORKER pid={pid}");
        Ok(pid)
    }

    fn restart(&mut self, closing: &AtomicBool) -> io::Result<()> {
        let old = self.stop("restart")?;
        if !closing.load(Ordering::Acquire) {
            let new = self.spawn()?;
            if let Some(old) = old {
                println!("WORKER_RESTARTED old={old} new={new}");
            } else {
                println!("WORKER_STARTED_AFTER_FAILURE new={new}");
            }
        }
        Ok(())
    }

    fn stop(&mut self, reason: &str) -> io::Result<Option<u32>> {
        let Some(child) = self.child.as_mut() else {
            return Ok(None);
        };
        let pid = child.id();
        drop(child.stdin.take());
        let deadline = Instant::now() + Duration::from_secs(6);
        loop {
            if let Some(status) = child.try_wait()? {
                self.child.take();
                println!(
                    "WORKER_EXIT pid={pid} reason={reason} success={}",
                    status.success()
                );
                // A confirmed exit releases the old worker even when it failed.
                // Quit still reports any failure to drain successfully.
                return if status.success() || reason == "restart" {
                    Ok(Some(pid))
                } else {
                    Err(io::Error::other("Native comparison inventory failed"))
                };
            }
            if Instant::now() >= deadline {
                child.kill()?;
                child.wait()?;
                self.child.take();
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Inventory did not exit after EOF",
                ));
            }
            thread::sleep(Duration::from_millis(10));
        }
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        // Startup failure, panic or a refused graceful stop must not orphan our worker.
        if let Some(child) = self.child.as_mut() {
            drop(child.stdin.take());
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{BufRead, BufReader, Write};
    use std::os::fd::OwnedFd;
    use std::os::unix::net::UnixStream;

    fn reporter(script: &str) -> io::Result<(Command, BufReader<UnixStream>)> {
        let (reader, writer) = UnixStream::pair()?;
        reader.set_read_timeout(Some(Duration::from_secs(4)))?;
        let mut cmd = Command::new("/bin/sh");
        cmd.args(["-c", script]).stdout(OwnedFd::from(writer));
        Ok((cmd, BufReader::new(reader)))
    }

    fn message(trace: &mut impl BufRead, label: &str) -> u32 {
        let mut line = String::new();
        trace.read_line(&mut line).unwrap();
        let (kind, pid) = line.trim_end().split_once(' ').unwrap();
        assert_eq!(kind, label);
        pid.parse().unwrap()
    }

    #[test]
    fn restart_reaps_the_first_process_and_quit_reaps_the_second_with_the_sender_held()
    -> io::Result<()> {
        let (command, mut trace) =
            reporter("printf 'start %s\\n' \"$$\"; read -r ignored; printf 'end %s\\n' \"$$\"")?;
        let bench = Benchmark::start_program(command)?;
        let requests = bench.restarts().unwrap();
        let first = message(&mut trace, "start");
        requests.request();
        assert_eq!(message(&mut trace, "end"), first);
        let second = message(&mut trace, "start");
        assert_ne!(first, second);
        assert!(!std::path::Path::new(&format!("/proc/{first}")).exists());
        bench.finish()?;
        assert_eq!(message(&mut trace, "end"), second);
        assert!(!std::path::Path::new(&format!("/proc/{second}")).exists());
        requests.request();
        Ok(())
    }

    #[test]
    fn quit_during_a_drain_supersedes_queued_restarts() -> io::Result<()> {
        let (command, mut trace) = reporter(
            r#"printf 'start %s\n' "$$"; read -r ignored; printf 'draining %s\n' "$$"; read -r resume <&1; printf 'end %s\n' "$$""#,
        )?;
        let bench = Benchmark::start_program(command)?;
        let requests = bench.restarts().unwrap();
        let pid = message(&mut trace, "start");
        requests.request();
        assert_eq!(message(&mut trace, "draining"), pid);
        requests.request();
        requests.request();
        let quitting = thread::spawn(move || bench.finish());
        let deadline = Instant::now() + Duration::from_secs(4);
        while !requests.closing.load(Ordering::Acquire) {
            assert!(Instant::now() < deadline);
            thread::sleep(Duration::from_millis(1));
        }
        writeln!(trace.get_mut(), "release")?;
        assert_eq!(message(&mut trace, "end"), pid);
        quitting.join().unwrap()?;
        assert!(trace.fill_buf()?.is_empty());
        Ok(())
    }

    #[test]
    fn a_failed_child_exit_is_reported_and_reaped() -> io::Result<()> {
        let (command, mut trace) =
            reporter("printf 'start %s\\n' \"$$\"; read -r ignored; exit 23")?;
        let bench = Benchmark::start_program(command)?;
        let pid = message(&mut trace, "start");
        assert!(bench.finish().is_err());
        assert!(!std::path::Path::new(&format!("/proc/{pid}")).exists());
        Ok(())
    }

    #[test]
    fn one_restart_recovers_an_exited_failed_worker() -> io::Result<()> {
        let failed = Command::new("/bin/false").spawn()?;
        let old = failed.id();
        let mut worker = Worker {
            command: Command::new("/bin/cat"),
            child: Some(failed),
        };
        worker.restart(&AtomicBool::new(false))?;
        let replacement = worker.child.as_mut().unwrap();
        assert_ne!(old, replacement.id());
        assert!(replacement.try_wait()?.is_none());
        assert!(!std::path::Path::new(&format!("/proc/{old}")).exists());
        worker.stop("quit")?;
        Ok(())
    }
}
