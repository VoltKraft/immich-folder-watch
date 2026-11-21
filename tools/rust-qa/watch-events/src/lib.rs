//! Native wakeups for a single, already authorized watch source.
//! Each subscription owns one bounded queue. Its generation and reasons remain
//! observable when the queue fills. The caller always schedules periodic inventories.

use std::collections::VecDeque;
use std::fs::File;
use std::io;
use std::sync::{Arc, Condvar, Mutex, mpsc};
use std::thread::{self, JoinHandle};
use std::time::Duration;

#[cfg(target_os = "linux")]
#[path = "linux.rs"]
mod native;
#[cfg(windows)]
#[path = "windows.rs"]
mod native;
#[cfg(any(windows, test))]
mod windows_status;
#[cfg(not(all(
    any(target_os = "linux", windows),
    any(target_arch = "x86_64", target_arch = "aarch64")
)))]
compile_error!("The native watch adapter requires Linux or Windows on x64 or ARM64");

/// Directory handles come from the caller's complete, handle-bound inventory.
/// The Linux backend needs a watch per authorized directory. Windows can arm
/// the kernel subtree watch on the root. Supply an empty slice for a flat source.
pub enum Scope<'a> {
    Direct,
    Tree {
        descendants: &'a [File],
        inventory_complete: bool,
    },
}

/// Reasons accumulate until a complete inventory acknowledges the same generation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u16)]
pub enum Reason {
    Initial = 1,
    Changed = 2,
    QueueFull = 4,
    NativeOverflow = 8,
    WatchLost = 16,
    CoverageIncomplete = 32,
    TreeChanged = 64,
    InventoryIncomplete = 128,
}

#[derive(Clone, Copy, Debug)]
pub struct Snapshot {
    pub generation: u64,
    pub acknowledged: u64,
    pub reasons: u16,
    pub requires_registration: bool,
    pub queued: usize,
    pub peak_queued: usize,
    pub coalesced: u64,
}

impl Snapshot {
    pub fn contains(&self, reason: Reason) -> bool {
        self.reasons & reason as u16 != 0
    }
}

/// Each hint belongs to this subscription's single source. It contains no path.
#[derive(Clone, Copy, Debug)]
pub struct Hint {
    pub generation: u64,
    pub reason: Reason,
}

struct State {
    snapshot: Snapshot,
    capacity: usize,
    hints: VecDeque<Hint>,
    confirmation_pending: bool,
}

struct Shared {
    state: Mutex<State>,
    wake: Condvar,
}

impl Shared {
    fn new(capacity: usize) -> Self {
        Self {
            state: Mutex::new(State {
                snapshot: Snapshot {
                    generation: 1,
                    acknowledged: 0,
                    reasons: Reason::Initial as u16,
                    requires_registration: false,
                    queued: 0,
                    peak_queued: 0,
                    coalesced: 0,
                },
                capacity,
                hints: VecDeque::with_capacity(capacity),
                confirmation_pending: false,
            }),
            wake: Condvar::new(),
        }
    }

    fn record(&self, reason: Reason) {
        let mut state = self.state.lock().expect("watch state poisoned");
        let generation = state.snapshot.generation.saturating_add(1);
        state.snapshot.generation = generation;
        state.snapshot.reasons |= reason as u16;
        if matches!(
            reason,
            Reason::CoverageIncomplete
                | Reason::WatchLost
                | Reason::TreeChanged
                | Reason::NativeOverflow
        ) {
            // A damaged subscription can only be replaced. A later comparison
            // must not declare an old descriptor set healthy again.
            state.snapshot.requires_registration = true;
            state.confirmation_pending = false;
        }
        if state.hints.len() < state.capacity {
            state.hints.push_back(Hint { generation, reason });
            state.snapshot.queued = state.hints.len();
            state.snapshot.peak_queued = state.snapshot.peak_queued.max(state.hints.len());
        } else {
            state.snapshot.coalesced = state.snapshot.coalesced.saturating_add(1);
            state.snapshot.reasons |= Reason::QueueFull as u16;
        }
        self.wake.notify_all();
    }
}

/// An inventory in progress. Dropping it leaves the source pending.
pub struct Inventory {
    source: Arc<Shared>,
    observed: Snapshot,
    finished: bool,
    pub hints: Vec<Hint>,
}

impl Inventory {
    pub fn observed(&self) -> Snapshot {
        self.observed
    }

    /// Acknowledges only a complete inventory that saw every outstanding generation.
    /// A partial inventory or a change during the scan requires another full scan.
    pub fn finish(mut self, complete: bool) -> bool {
        self.finished = true;
        if !complete {
            self.source.record(Reason::InventoryIncomplete);
            return false;
        }
        let mut state = self.source.state.lock().expect("watch state poisoned");
        if state.confirmation_pending
            || state.snapshot.generation != self.observed.generation
            || state.snapshot.generation == u64::MAX
        {
            return false;
        }
        state.snapshot.acknowledged = state.snapshot.generation;
        state.snapshot.reasons = 0;
        true
    }
}

impl Drop for Inventory {
    fn drop(&mut self) {
        if !self.finished {
            self.source.record(Reason::InventoryIncomplete);
        }
    }
}

pub struct Watch {
    shared: Arc<Shared>,
    stop: native::Stop,
    done: mpsc::Receiver<()>,
    thread: Option<JoinHandle<io::Result<()>>>,
    #[cfg(target_os = "linux")]
    registration: Arc<native::Registration>,
}

impl Watch {
    /// Start the native provider and inspect the initial snapshot for coverage
    /// or loss requiring replacement. A start error requires the caller's regular
    /// inventory fallback. Queue size must be between 1 and 256.
    pub fn start(directory: &File, scope: Scope<'_>, capacity: usize) -> io::Result<Self> {
        if !(1..=256).contains(&capacity) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "hint capacity must be 1 to 256",
            ));
        }
        let metadata = directory.metadata();
        #[cfg(windows)]
        let metadata = native::observed("directory metadata", metadata);
        if !metadata?.is_dir() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "a directory and bounded hint capacity are required",
            ));
        }
        let shared = Arc::new(Shared::new(capacity));
        #[cfg(target_os = "linux")]
        if matches!(scope, Scope::Tree { .. }) {
            let mut initial = shared.state.lock().expect("watch state poisoned");
            initial.confirmation_pending = true;
            initial.snapshot.requires_registration = true;
        }
        if matches!(
            scope,
            Scope::Tree {
                inventory_complete: false,
                ..
            }
        ) {
            shared.record(Reason::CoverageIncomplete);
        }
        let (stop, backend) = native::prepare(directory, scope, &shared)?;
        #[cfg(target_os = "linux")]
        let registration = Arc::clone(&backend.registration);
        let events = Arc::clone(&shared);
        let (ready_tx, ready_rx) = mpsc::sync_channel(1);
        let (done_tx, done) = mpsc::sync_channel(1);
        let thread = thread::Builder::new()
            .name("watch-hints".into())
            .spawn(move || {
                let result = backend.run(&events, ready_tx);
                if result.is_err() {
                    events.record(Reason::WatchLost);
                }
                let _ = done_tx.send(());
                result
            })?;
        let mut watch = Self {
            shared,
            stop,
            done,
            thread: Some(thread),
            #[cfg(target_os = "linux")]
            registration,
        };
        if ready_rx.recv().is_err() {
            watch.join()?;
            return Err(io::Error::other(
                "watch provider exited before registration",
            ));
        }
        Ok(watch)
    }

    /// Compare the armed Linux watch identities with a second, complete,
    /// authorized enumeration performed after startup. A changed set invalidates
    /// this subscription. Install its replacement before retiring it. A partial
    /// or unavailable enumeration must be supplied as None.
    #[cfg(target_os = "linux")]
    pub fn confirm_directory_set(
        &self,
        root: &File,
        descendants: Option<&[File]>,
    ) -> io::Result<bool> {
        match descendants
            .map(|children| self.registration.matches(root, children))
            .transpose()
        {
            Ok(Some(true)) => {
                let mut state = self.shared.state.lock().expect("watch state poisoned");
                if state.confirmation_pending {
                    state.confirmation_pending = false;
                    state.snapshot.requires_registration = false;
                }
                Ok(!state.snapshot.requires_registration)
            }
            outcome => {
                self.shared.record(Reason::CoverageIncomplete);
                outcome.map(|_| false)
            }
        }
    }

    pub fn snapshot(&self) -> Snapshot {
        self.shared
            .state
            .lock()
            .expect("watch state poisoned")
            .snapshot
    }

    /// Return the latest state on change or timeout. A periodic inventory can
    /// proceed on timeout even when the host never delivers a native event.
    pub fn wait_after(&self, generation: u64, timeout: Duration) -> Snapshot {
        let state = self.shared.state.lock().expect("watch state poisoned");
        self.shared
            .wake
            .wait_timeout_while(state, timeout, |s| s.snapshot.generation == generation)
            .expect("watch state poisoned")
            .0
            .snapshot
    }

    pub fn begin_inventory(&self) -> Inventory {
        let mut state = self.shared.state.lock().expect("watch state poisoned");
        let observed = state.snapshot;
        let hints = state.hints.drain(..).collect();
        state.snapshot.queued = 0;
        Inventory {
            source: Arc::clone(&self.shared),
            observed,
            finished: false,
            hints,
        }
    }

    /// On timeout the caller retains ownership and may wait again. The final
    /// owner joins the native worker before releasing its OS I/O resources.
    pub fn stop_and_join(&mut self, timeout: Duration) -> io::Result<()> {
        if self.thread.is_none() {
            return Ok(());
        }
        self.stop.signal()?;
        if let Err(mpsc::RecvTimeoutError::Timeout) = self.done.recv_timeout(timeout) {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "native watch has not drained",
            ));
        }
        self.join()
    }

    fn join(&mut self) -> io::Result<()> {
        match self.thread.take() {
            Some(handle) => handle
                .join()
                .map_err(|_| io::Error::other("watch worker panicked"))?,
            None => Ok(()),
        }
    }
}

impl Drop for Watch {
    fn drop(&mut self) {
        if self.thread.is_some() {
            let _ = self.stop.signal();
            let _ = self.join();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn inventory(shared: &Arc<Shared>) -> Inventory {
        Inventory {
            source: Arc::clone(shared),
            observed: shared.state.lock().unwrap().snapshot,
            finished: false,
            hints: Vec::new(),
        }
    }

    #[test]
    fn cancelling_a_periodic_inventory_after_a_clean_ack_requests_another_scan() {
        let source = Arc::new(Shared::new(1));
        assert!(inventory(&source).finish(true));
        let cancelled = inventory(&source);
        let overlapping = inventory(&source);
        assert_eq!(cancelled.observed().reasons, 0);
        drop(cancelled);
        assert!(!overlapping.finish(true));
        let retry = inventory(&source);
        assert!(retry.observed().contains(Reason::InventoryIncomplete));
        assert!(retry.observed().generation > retry.observed().acknowledged);
        assert!(retry.finish(true));
    }

    #[test]
    fn failed_and_overtaken_inventories_cannot_clear_pending_work() {
        let source = Arc::new(Shared::new(1));
        let older = inventory(&source);
        source.record(Reason::Changed);
        assert!(!older.finish(true));
        let before_partial = inventory(&source);
        assert!(!inventory(&source).finish(false));
        assert!(!before_partial.finish(true));
        let next = inventory(&source);
        assert!(next.observed().contains(Reason::InventoryIncomplete));
        assert!(next.finish(true));
    }

    #[test]
    fn coverage_loss_survives_inventory_acknowledgement() {
        let source = Arc::new(Shared::new(2));
        source.record(Reason::WatchLost);
        assert!(inventory(&source).finish(true));
        let state = source.state.lock().unwrap().snapshot;
        assert!(state.requires_registration);
        assert_eq!(state.acknowledged, state.generation);
    }

    #[test]
    fn generation_exhaustion_never_acknowledges_newer_work() {
        let source = Arc::new(Shared::new(1));
        source.state.lock().unwrap().snapshot.generation = u64::MAX;
        let older = inventory(&source);
        source.record(Reason::Changed);
        assert!(!older.finish(true));
    }
}
