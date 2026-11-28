//! One-shot readiness for the visible WARP root. The painter and winit pump share one UI thread.
use std::cell::RefCell;
use std::io;
use std::marker::PhantomData;
use std::rc::Rc;
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::io::{AsRawHandle as _, BorrowedHandle, OwnedHandle};
#[cfg(not(windows))]
type OwnedHandle = usize;

const WATCHDOG: Duration = Duration::from_secs(2);
const LIMIT: usize = 65_536;

#[derive(Clone, Copy, Eq, PartialEq)]
struct Key {
    generation: u64,
    token: u64,
    hwnd: u64,
}

enum Phase {
    Armed(Rc<OwnedHandle>, Box<dyn FnOnce()>),
    Ready,
    Drawing,
    Presenting,
}

struct Request {
    key: Key,
    deadline: Instant,
    phase: Phase,
}

struct Row {
    event: &'static str,
    key: Key,
    begin: i64,
    end: i64,
}

struct Slot {
    generation: u64,
    hwnd: u64,
    waited_in_pump: bool,
}

#[derive(Default)]
struct State {
    session: bool,
    serial: u64,
    request: Option<Request>,
    // A successful wait can consume one frame slot. Hiding cancels the redraw, but
    // the same swapchain must not wait a second time before its next real present.
    credit: Option<Slot>,
    rows: Vec<Row>,
    immediate: u64,
    dropped: usize,
}

impl State {
    fn next(&mut self) -> u64 {
        self.serial = self
            .serial
            .checked_add(1)
            .expect("Readiness identity overflow");
        self.serial
    }

    fn mark(&mut self, event: &'static str, key: Key, begin: i64, end: i64) {
        if self.rows.len() == LIMIT {
            self.dropped += 1;
        } else {
            self.rows.push(Row {
                event,
                key,
                begin,
                end,
            });
        }
    }

    fn stamp(&mut self, event: &'static str, key: Key) {
        let now = clock();
        self.mark(event, key, now, now);
    }

    fn cancel(&mut self) {
        // A synchronous HWND notification may arrive inside queue.present. Its slot
        // is already spent; finish the actual call before recording the result.
        if self
            .request
            .as_ref()
            .is_some_and(|r| matches!(r.phase, Phase::Presenting))
        {
            return;
        }
        if let Some(r) = self.request.take() {
            self.stamp(
                if matches!(r.phase, Phase::Drawing) {
                    "discard"
                } else {
                    "cancel"
                },
                r.key,
            );
        }
    }
}

thread_local! {
    static STATE: RefCell<State> = RefCell::new(State::default());
}

fn access<T>(f: impl FnOnce(&mut State) -> T) -> T {
    STATE.with_borrow_mut(f)
}

/// Install before constructing the event loop and finish after all renderer and native window teardown.
pub struct Session(PhantomData<Rc<()>>);

impl Session {
    pub fn start() -> Self {
        access(|s| {
            assert!(
                !s.session && s.rows.is_empty() && s.request.is_none(),
                "Duplicate frame-readiness session"
            );
            s.session = true;
        });
        Self(PhantomData)
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        use std::io::Write as _;
        let mut output = io::BufWriter::new(io::stderr().lock());
        access(|s| {
            s.cancel();
            writeln!(
                output,
                "FRAME_READY_BEGIN pid={} tid={} hz={} count={} dropped={}",
                std::process::id(),
                thread(),
                frequency(),
                s.rows.len(),
                s.dropped
            )
            .unwrap();
            for row in &s.rows {
                writeln!(
                    output,
                    "FRAME_READY {} {} {} {} {} {}",
                    row.event, row.key.generation, row.key.token, row.key.hwnd, row.begin, row.end
                )
                .unwrap();
            }
            writeln!(output, "FRAME_READY_END immediate={}", s.immediate).unwrap();
            output.flush().unwrap();
            s.session = false;
        });
    }
}

/// Owned by a single painter surface. The marker restricts mutation and destruction to its UI thread.
pub struct SurfaceGate {
    generation: u64,
    _ui: PhantomData<Rc<()>>,
}

impl Default for SurfaceGate {
    fn default() -> Self {
        Self {
            generation: access(State::next),
            _ui: PhantomData,
        }
    }
}

impl SurfaceGate {
    /// Retire the current swapchain's registration before configuring its replacement.
    pub fn invalidate(&mut self) {
        self.cancel();
        self.generation = access(State::next);
    }

    fn cancel(&self) {
        access(|s| {
            if s.request
                .as_ref()
                .is_some_and(|r| r.key.generation == self.generation)
            {
                s.cancel();
            }
            if s.credit
                .as_ref()
                .is_some_and(|slot| slot.generation == self.generation)
            {
                s.credit = None;
            }
        });
    }

    /// A busy first check lends no HANDLE to winit. Only its owned kernel duplicate reaches the pump.
    pub fn admit(
        &self,
        hwnd: u64,
        now: Instant,
        probe: impl FnOnce() -> io::Result<Option<OwnedHandle>>,
        redraw: impl FnOnce() + 'static,
    ) -> io::Result<Option<Instant>> {
        access(|s| {
            if let Some(r) = s.request.as_mut() {
                if r.key.generation != self.generation || r.key.hwnd != hwnd {
                    return Err(io::Error::other(
                        "Unexpected frame-ready root or swapchain generation",
                    ));
                }
                match r.phase {
                    Phase::Armed(..) => {
                        if now >= r.deadline {
                            s.cancel();
                            return Err(io::Error::new(
                                io::ErrorKind::TimedOut,
                                "Unsignalled root frame at watchdog deadline",
                            ));
                        }
                        return Ok(Some(r.deadline));
                    }
                    Phase::Ready => {
                        r.phase = Phase::Drawing;
                        let key = r.key;
                        s.stamp("consume", key);
                        return Ok(None);
                    }
                    // A surface operation aborted the admitted frame before queue.present.
                    Phase::Drawing => s.cancel(),
                    Phase::Presenting => {
                        return Err(io::Error::other("Reentrant root paint during present"));
                    }
                }
            }
            if let Some(slot) = &s.credit
                && (slot.generation, slot.hwnd) == (self.generation, hwnd)
            {
                if !slot.waited_in_pump {
                    return Ok(None);
                }
                // The prior redraw was abandoned after DXGI had granted the slot.
                // This is a new repaint with its own identity and no kernel wait.
                let key = Key {
                    generation: self.generation,
                    token: s.next(),
                    hwnd,
                };
                s.request = Some(Request {
                    key,
                    deadline: now,
                    phase: Phase::Drawing,
                });
                s.stamp("reuse", key);
                return Ok(None);
            }
            let Some(duplicate) = probe()? else {
                s.credit = Some(Slot {
                    generation: self.generation,
                    hwnd,
                    waited_in_pump: false,
                });
                s.immediate += 1;
                return Ok(None);
            };
            let key = Key {
                generation: self.generation,
                token: s.next(),
                hwnd,
            };
            let deadline = now + WATCHDOG;
            s.request = Some(Request {
                key,
                deadline,
                phase: Phase::Armed(Rc::new(duplicate), Box::new(redraw)),
            });
            s.stamp("arm", key);
            Ok(Some(deadline))
        })
    }

    pub fn present<T>(&self, submit: impl FnOnce() -> T) -> T {
        let key = access(|s| {
            if s.credit
                .as_ref()
                .is_some_and(|slot| slot.generation == self.generation)
            {
                s.credit = None;
            }
            let r = s.request.as_mut().filter(|r| {
                r.key.generation == self.generation && matches!(r.phase, Phase::Drawing)
            })?;
            r.phase = Phase::Presenting;
            Some(r.key)
        });
        if let Some(key) = key {
            let begin = clock();
            let value = submit();
            let end = clock();
            access(|s| {
                if s.request
                    .as_ref()
                    .is_some_and(|r| r.key == key && matches!(r.phase, Phase::Presenting))
                {
                    s.request.take();
                    s.mark("present", key, begin, end);
                }
            });
            value
        } else {
            submit()
        }
    }
}

impl Drop for SurfaceGate {
    fn drop(&mut self) {
        self.cancel();
    }
}

/// A retained HWND can hide without another painter call. Disarm before its native visibility change.
pub fn cancel_window(hwnd: u64) {
    access(|s| {
        if s.request.as_ref().is_some_and(|r| r.key.hwnd == hwnd) {
            s.cancel();
        }
    });
}

/// Record entry to the real WM_CLOSE branch before its ordinary handler runs.
pub fn native_close(hwnd: u64) {
    access(|s| {
        if let Some(r) = &s.request
            && r.key.hwnd == hwnd
            && matches!(r.phase, Phase::Armed(..))
        {
            s.stamp("close", r.key);
        }
    });
}

/// The duplicate stays live across the whole outer wait even if the registration is retired.
pub struct WaitLease {
    key: Key,
    handle: Rc<OwnedHandle>,
}

pub fn wait_lease() -> Option<WaitLease> {
    access(|s| {
        let r = s.request.as_ref()?;
        let Phase::Armed(handle, _) = &r.phase else {
            return None;
        };
        Some(WaitLease {
            key: r.key,
            handle: Rc::clone(handle),
        })
    })
}

impl WaitLease {
    #[cfg(windows)]
    pub fn handle(&self) -> std::os::windows::io::RawHandle {
        self.handle.as_raw_handle()
    }

    /// winit places its optional timer first, our frame last and the queue after both.
    pub fn returned(self, result: u32, timer: bool) -> io::Result<()> {
        let frame = u32::from(timer);
        match result {
            index if index == frame => return self.signalled(Instant::now()),
            index if index == frame + 1 => self.input_returned(),
            0 | 258 => (), // Original high-resolution timer or WAIT_TIMEOUT.
            u32::MAX => return Err(io::Error::last_os_error()),
            _ => return Err(io::Error::other("Unexpected Windows message-wait result")),
        }
        Ok(())
    }

    /// Transfer exactly the result already consumed by the native wait to one repaint.
    fn signalled(self, now: Instant) -> io::Result<()> {
        let wake = access(|s| {
            let Some(r) = s.request.as_mut() else {
                return Ok(None);
            };
            if r.key != self.key || !matches!(r.phase, Phase::Armed(..)) {
                return Ok(None);
            }
            if now >= r.deadline {
                s.cancel();
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Late root frame signal",
                ));
            }
            let Phase::Armed(_, wake) = std::mem::replace(&mut r.phase, Phase::Ready) else {
                unreachable!()
            };
            s.credit = Some(Slot {
                generation: self.key.generation,
                hwnd: self.key.hwnd,
                waited_in_pump: true,
            });
            s.stamp("signal", self.key);
            Ok(Some(wake))
        })?;
        if let Some(wake) = wake {
            wake();
        }
        Ok(())
    }

    pub fn input_returned(&self) {
        access(|s| {
            if s.request
                .as_ref()
                .is_some_and(|r| r.key == self.key && matches!(r.phase, Phase::Armed(..)))
            {
                s.stamp("input", self.key);
            }
        });
    }
}

/// Called with the HAL surface guard held. Duplicate only the busy handle, before releasing that guard.
#[cfg(windows)]
pub fn probe(handle: BorrowedHandle<'_>) -> io::Result<Option<OwnedHandle>> {
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn WaitForSingleObject(handle: std::os::windows::io::RawHandle, timeout: u32) -> u32;
    }
    // The borrowed handle is live for the zero-time system call and the optional duplication.
    match unsafe { WaitForSingleObject(handle.as_raw_handle(), 0) } {
        0 => Ok(None),
        258 => handle.try_clone_to_owned().map(Some),
        0xffff_ffff => Err(io::Error::last_os_error()),
        _ => Err(io::Error::other("Unexpected DXGI readiness result")),
    }
}

#[cfg(windows)]
fn clock() -> i64 {
    super::clock()
}

#[cfg(windows)]
fn thread() -> u32 {
    unsafe { super::GetCurrentThreadId() }
}

#[cfg(windows)]
fn frequency() -> i64 {
    let mut hz = 0;
    assert_ne!(unsafe { super::QueryPerformanceFrequency(&raw mut hz) }, 0);
    hz
}

#[cfg(not(windows))]
fn clock() -> i64 {
    1
}
#[cfg(not(windows))]
fn thread() -> u32 {
    1
}
#[cfg(not(windows))]
fn frequency() -> i64 {
    1
}

#[cfg(all(test, not(windows)))]
mod tests {
    use super::*;
    use std::cell::Cell;

    fn reset() {
        access(|s| *s = State::default());
    }
    fn events() -> Vec<&'static str> {
        access(|s| s.rows.iter().map(|r| r.event).collect())
    }

    #[test]
    fn immediate_frame_never_registers_or_enters_the_outer_wait() {
        reset();
        let g = SurfaceGate::default();
        assert!(
            g.admit(7, Instant::now(), || Ok(None), || panic!())
                .unwrap()
                .is_none()
        );
        assert!(wait_lease().is_none());
        assert!(g.present(|| true));
        assert_eq!(access(|s| s.immediate), 1);
    }

    #[test]
    fn message_wakeup_keeps_the_pending_handle_and_signal_is_consumed_once() {
        reset();
        let gate = SurfaceGate::default();
        let now = Instant::now();
        let count = Rc::new(Cell::new(0));
        let called = Rc::clone(&count);
        let deadline = gate
            .admit(
                7,
                now,
                || Ok(Some(63)),
                move || called.set(called.get() + 1),
            )
            .unwrap();
        let input = wait_lease().unwrap();
        assert_eq!(*input.handle, 63);
        input.input_returned();
        assert_eq!(
            gate.admit(7, now, || panic!("second poll"), || panic!())
                .unwrap(),
            deadline
        );
        wait_lease().unwrap().signalled(Instant::now()).unwrap();
        input.signalled(Instant::now()).unwrap();
        assert!(wait_lease().is_none());
        assert_eq!(count.get(), 1);
        assert!(
            gate.admit(7, now, || panic!("already signalled"), || panic!())
                .unwrap()
                .is_none()
        );
        gate.present(|| {});
        assert_eq!(events(), ["arm", "input", "signal", "consume", "present"]);
    }

    #[test]
    fn hide_and_swapchain_replacement_reject_stale_leases_on_the_same_hwnd() {
        reset();
        let now = Instant::now();
        let mut gate = SurfaceGate::default();
        gate.admit(7, now, || Ok(Some(42)), || panic!()).unwrap();
        let hidden = wait_lease().unwrap();
        cancel_window(7);
        gate.admit(7, now, || Ok(Some(43)), || panic!()).unwrap();
        hidden.signalled(Instant::now()).unwrap();
        let replaced = wait_lease().unwrap();
        gate.invalidate();
        gate.admit(7, now, || Ok(Some(44)), || {}).unwrap();
        replaced.signalled(Instant::now()).unwrap();
        wait_lease().unwrap().signalled(Instant::now()).unwrap();
        gate.admit(7, now, || panic!(), || panic!()).unwrap();
        drop(gate);
        assert_eq!(
            events(),
            [
                "arm", "cancel", "arm", "cancel", "arm", "signal", "consume", "discard"
            ]
        );
    }

    #[test]
    fn failures_and_watchdog_do_not_admit_an_unready_frame() {
        reset();
        let gate = SurfaceGate::default();
        let now = Instant::now();
        assert!(
            gate.admit(7, now, || Err(io::Error::other("handle")), || {})
                .is_err()
        );
        gate.admit(7, now, || Ok(Some(77)), || panic!()).unwrap();
        assert!(gate.admit(8, now, || panic!(), || panic!()).is_err());
        assert_eq!(
            gate.admit(7, now + WATCHDOG, || panic!(), || panic!())
                .unwrap_err()
                .kind(),
            io::ErrorKind::TimedOut
        );
        assert!(wait_lease().is_none());
        gate.admit(7, now, || Ok(Some(78)), || panic!()).unwrap();
        assert_eq!(
            wait_lease()
                .unwrap()
                .signalled(now + WATCHDOG)
                .unwrap_err()
                .kind(),
            io::ErrorKind::TimedOut
        );
        assert!(wait_lease().is_none());
        drop(gate);
    }

    #[test]
    fn queue_timer_timeout_and_close_are_distinct_from_the_frame_slot() {
        for timer in [false, true] {
            reset();
            let gate = SurfaceGate::default();
            gate.admit(7, Instant::now(), || Ok(Some(2)), || {})
                .unwrap();
            let frame = u32::from(timer);
            let lease = || wait_lease().unwrap();
            if timer {
                lease().returned(0, timer).unwrap();
            }
            lease().returned(258, timer).unwrap();
            assert!(lease().returned(128, timer).is_err());
            assert!(lease().returned(u32::MAX, timer).is_err());
            lease().returned(frame + 1, timer).unwrap();
            native_close(8);
            native_close(7);
            lease().returned(frame, timer).unwrap();
            native_close(7);
            assert_eq!(events(), ["arm", "input", "close", "signal"]);
        }
    }

    #[test]
    fn hiding_after_a_signal_preserves_the_frame_slot_only_until_present_or_reconfigure() {
        reset();
        let mut gate = SurfaceGate::default();
        let now = Instant::now();
        gate.admit(7, now, || Ok(Some(42)), || {}).unwrap();
        wait_lease().unwrap().signalled(Instant::now()).unwrap();
        cancel_window(7);
        assert!(wait_lease().is_none());
        assert!(
            gate.admit(7, now, || panic!("slot already acquired"), || {})
                .unwrap()
                .is_none()
        );
        gate.present(|| {});
        gate.admit(7, now, || Ok(None), || {}).unwrap();
        gate.invalidate();
        assert!(
            gate.admit(7, now, || Ok(Some(43)), || {})
                .unwrap()
                .is_some()
        );
        assert_eq!(
            events(),
            ["arm", "signal", "cancel", "reuse", "present", "arm"]
        );
    }

    #[test]
    fn hiding_inside_a_real_present_does_not_restore_its_spent_slot() {
        reset();
        let gate = SurfaceGate::default();
        let now = Instant::now();
        gate.admit(7, now, || Ok(Some(42)), || {}).unwrap();
        wait_lease().unwrap().signalled(now).unwrap();
        gate.admit(7, now, || panic!(), || {}).unwrap();
        gate.present(|| cancel_window(7));
        assert!(
            gate.admit(7, now, || Ok(Some(43)), || {})
                .unwrap()
                .is_some()
        );
        assert_eq!(events(), ["arm", "signal", "consume", "present", "arm"]);
    }
}
