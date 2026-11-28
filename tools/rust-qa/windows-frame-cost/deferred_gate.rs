//! Bound the isolated DX12 comparison's retry frequency and lifetime.
use std::io;
use std::time::{Duration, Instant};

const RETRY: Duration = Duration::from_millis(16);
const LIMIT: Duration = Duration::from_secs(2);

#[derive(Default)]
pub(super) struct Gate {
    pending: Option<(Instant, Instant)>,
    signalled: u64,
    timeouts: u64,
    resumed: u64,
    early_callbacks: u64,
    awaiting_present: Option<i64>,
    presents: Vec<(u32, i64, i64, i64)>,
    dropped: u64,
}

impl Gate {
    pub(super) fn reset(&mut self) {
        self.pending = None;
        self.awaiting_present = None;
    }

    pub(super) fn poll(
        &mut self,
        now: Instant,
        check: impl FnOnce() -> io::Result<bool>,
    ) -> io::Result<Option<Instant>> {
        self.awaiting_present = None;
        let first = if let Some((first, next)) = self.pending {
            if now < next {
                self.early_callbacks += 1;
                return Ok(Some(next));
            }
            first
        } else {
            now
        };
        if check()? {
            self.signalled += 1;
            if self.pending.take().is_some() {
                self.resumed += 1;
                self.awaiting_present = Some(clock());
            }
            return Ok(None);
        }
        self.timeouts += 1;
        if now.duration_since(first) >= LIMIT {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "DX12 frame remained unavailable",
            ));
        }
        let next = now + RETRY;
        self.pending = Some((first, next));
        Ok(Some(next))
    }
    pub(super) fn present(&mut self, operation: impl FnOnce()) {
        if let Some(ready) = self.awaiting_present.take() {
            let start = clock();
            operation();
            let end = clock();
            if self.presents.len() < 8192 {
                self.presents.push((thread(), ready, start, end));
            } else {
                self.dropped += 1;
            }
        } else {
            operation();
        }
    }
}

#[cfg(windows)]
fn clock() -> i64 {
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn QueryPerformanceCounter(value: *mut i64) -> i32;
    }
    let mut value = 0;
    unsafe { QueryPerformanceCounter(&mut value) };
    value
}

#[cfg(windows)]
fn thread() -> u32 {
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetCurrentThreadId() -> u32;
    }
    unsafe { GetCurrentThreadId() }
}

#[cfg(not(windows))]
fn thread() -> u32 {
    0
}

#[cfg(not(windows))]
fn clock() -> i64 {
    0
}

impl Drop for Gate {
    fn drop(&mut self) {
        eprintln!(
            "DEFERRED_FRAME signalled={} timeouts={} resumed={} early_callbacks={} dropped={}",
            self.signalled, self.timeouts, self.resumed, self.early_callbacks, self.dropped
        );
        for (tid, ready, start, end) in &self.presents {
            eprintln!("DEFERRED_PRESENT {tid} {ready} {start} {end}");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_premature_callback_reuses_the_deadline_without_polling() {
        let mut gate = Gate::default();
        let now = Instant::now();
        assert_eq!(gate.poll(now, || Ok(false)).unwrap(), Some(now + RETRY));
        assert_eq!(
            gate.poll(now + RETRY / 2, || panic!()).unwrap(),
            Some(now + RETRY)
        );
        assert_eq!(gate.poll(now + RETRY, || Ok(true)).unwrap(), None);
        gate.present(|| {});
        assert_eq!(gate.presents.len(), 1);
        assert_eq!(
            (
                gate.signalled,
                gate.timeouts,
                gate.resumed,
                gate.early_callbacks
            ),
            (1, 1, 1, 1)
        );
    }

    #[test]
    fn an_unavailable_or_failed_handle_is_bounded_and_hiding_cancels_the_retry() {
        let mut gate = Gate::default();
        let now = Instant::now();
        gate.poll(now, || Ok(false)).unwrap();
        assert_eq!(
            gate.poll(now + LIMIT, || Ok(false)).unwrap_err().kind(),
            io::ErrorKind::TimedOut
        );
        gate.reset();
        assert_eq!(
            gate.poll(now + LIMIT, || Ok(false)).unwrap(),
            Some(now + LIMIT + RETRY)
        );
        gate.reset();
        assert!(
            gate.poll(now, || Err(io::Error::other("failed handle")))
                .is_err()
        );
    }
}
