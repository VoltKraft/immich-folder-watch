//! Schedule Shell re-registration and retain events until the GUI's bounded queue accepts them.
use std::sync::mpsc::TrySendError;
use std::time::{Duration, Instant};

pub(crate) type Host = (usize, u32); // Shell_TrayWnd HWND and its process ID.

#[derive(Default)]
pub(crate) struct BoundHost<T>(Option<(Host, T)>);

impl<T> BoundHost<T> {
    /// Replace the previous binding on every acknowledgement, including an unverified one.
    pub(crate) fn confirm(
        &mut self,
        before: Option<(Host, T)>,
        after: Option<Host>,
        still_running: impl FnOnce(&T) -> bool,
    ) -> Option<Host> {
        self.0 = before.filter(|(host, process)| Some(*host) == after && still_running(process));
        self.0.as_ref().map(|(host, _)| *host)
    }

    pub(crate) fn clear(&mut self) {
        self.0 = None;
    }

    pub(crate) fn modified(
        &mut self,
        before: Option<Host>,
        after: Option<Host>,
        still_running: impl FnOnce(&T) -> bool,
    ) {
        let original = self.0.take();
        if before == after {
            self.confirm(original, after, still_running);
        }
    }

    pub(crate) fn departed(
        &self,
        signaled: impl FnOnce(&T) -> bool,
        shell_and_icon_absent: impl FnOnce() -> bool,
    ) -> Option<Host> {
        let (host, process) = self.0.as_ref()?;
        (signaled(process) && shell_and_icon_absent()).then_some(*host)
    }
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Attempt {
    Recreate,
    Retry,
}

pub(crate) struct Recovery {
    pub(crate) host: Option<Host>,
    retry_at: Option<Instant>,
    delay: Duration,
}

impl Recovery {
    const FIRST_DELAY: Duration = Duration::from_secs(3);

    pub(crate) fn new(host: Option<Host>) -> Self {
        Self {
            host,
            retry_at: None,
            delay: Self::FIRST_DELAY,
        }
    }

    pub(crate) fn observe(
        &mut self,
        current: Option<Host>,
        taskbar_created: bool,
        now: Instant,
    ) -> Option<Attempt> {
        if current != self.host || taskbar_created {
            *self = Self::new(current);
            return current.map(|_| Attempt::Recreate);
        }
        if self.retry_at.is_some_and(|due| now >= due) {
            self.retry_at = None;
            return Some(Attempt::Retry);
        }
        None
    }

    pub(crate) fn result(&mut self, acknowledged: bool, now: Instant) {
        if self.host.is_some() && !acknowledged {
            self.retry_at = Some(now + self.delay);
            self.delay = (self.delay * 2).min(Duration::from_secs(30));
        } else {
            self.retry_at = None;
            self.delay = Self::FIRST_DELAY;
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TrayEvent {
    Availability(bool),
    Open(u32),
}

#[derive(Default)]
pub(crate) struct Pending {
    pub(crate) available: Option<bool>,
    pub(crate) open: Option<u32>,
}

impl Pending {
    pub(crate) fn flush<T>(
        &mut self,
        send: &impl Fn(TrayEvent) -> Result<(), TrySendError<T>>,
    ) -> Result<Option<u32>, TrySendError<T>> {
        if let Some(available) = self.available {
            send(TrayEvent::Availability(available))?;
            self.available = None;
        }
        if let Some(ordinal) = self.open {
            send(TrayEvent::Open(ordinal))?;
            self.open = None;
            return Ok(Some(ordinal));
        }
        Ok(None)
    }
}
