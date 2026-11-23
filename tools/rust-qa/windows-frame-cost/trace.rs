//! Bounded measurements of the isolated dispatch subject's own threads.
use std::cell::Cell;
use std::ffi::c_void;
use std::io::{BufWriter, Write};
use std::marker::PhantomData;
use std::rc::Rc;
use std::sync::{Mutex, OnceLock};

const LIMIT: usize = 262_144;
type Handle = *mut c_void;

// winnt.h PERFORMANCE_DATA, with MAX_HW_COUNTERS set to 16. Hardware counters are never enabled.
#[repr(C)]
#[derive(Default)]
struct HardwareCounter {
    kind: u32,
    reserved: u32,
    value: u64,
}
#[repr(C)]
#[derive(Default)]
struct PerformanceData {
    size: u16,
    version: u8,
    hardware_count: u8,
    switches: u32,
    reasons: u64,
    cycles: u64,
    retries: u32,
    reserved: u32,
    hardware: [HardwareCounter; 16],
}
const _: () = assert!(size_of::<PerformanceData>() == 288);
#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetCurrentThread() -> Handle;
    fn GetCurrentThreadId() -> u32;
    fn QueryPerformanceCounter(value: *mut i64) -> i32;
    fn QueryPerformanceFrequency(value: *mut i64) -> i32;
    fn EnableThreadProfiling(
        thread: Handle,
        flags: u32,
        hardware: u64,
        profile: *mut Handle,
    ) -> u32;
    fn ReadThreadProfilingData(profile: Handle, flags: u32, data: *mut PerformanceData) -> u32;
    fn DisableThreadProfiling(profile: Handle) -> u32;
    fn QueryThreadCycleTime(thread: Handle, cycles: *mut u64) -> i32;
}

struct Profile {
    handle: Handle,
    status: u32,
}
impl Profile {
    fn new() -> Self {
        let mut handle = std::ptr::null_mut();
        // Windows permits the current thread only. Request dispatch statistics and zero hardware counters.
        let status = unsafe { EnableThreadProfiling(GetCurrentThread(), 1, 0, &mut handle) };
        Self { handle, status }
    }
    fn sample(&self) -> (u32, u32, u64, i64) {
        let mut data = PerformanceData {
            size: size_of::<PerformanceData>() as u16,
            version: 1,
            ..Default::default()
        };
        let status = if self.status == 0 {
            unsafe { ReadThreadProfilingData(self.handle, 1, &mut data) }
        } else {
            self.status
        };
        if status == 0 {
            (0, data.switches, data.reasons, data.cycles as i64)
        } else {
            let mut cycles = 0;
            let ok = unsafe { QueryThreadCycleTime(GetCurrentThread(), &mut cycles) };
            (status, 0, 0, if ok == 0 { -1 } else { cycles as i64 })
        }
    }
}
impl Drop for Profile {
    fn drop(&mut self) {
        if self.status == 0 {
            unsafe {
                DisableThreadProfiling(self.handle);
            }
        }
    }
}
thread_local! {
    static PROFILE: Profile = Profile::new();
    static PARENT: Cell<u64> = const { Cell::new(0) };
}
struct Entry {
    id: u64,
    parent: u64,
    stage: &'static str,
    ending: bool,
    thread: u32,
    before: i64,
    after: i64,
    status: u32,
    switches: u32,
    reasons: u64,
    cycles: i64,
    value: i64,
    call_start: i64,
    call_end: i64,
    hwnd: i64,
}
struct Log {
    rows: Vec<Entry>,
    lost: usize,
    next: u64,
}
static LOG: OnceLock<Option<Mutex<Log>>> = OnceLock::new();
fn log() -> Option<&'static Mutex<Log>> {
    LOG.get_or_init(|| {
        [
            "IFW_QA_ISOLATED",
            "IFW_QA_WINDOWS_DISPATCH",
            "IFW_QA_WINDOWS_FRAME_COST",
        ]
        .iter()
        .all(|name| std::env::var(name).as_deref() == Ok("1"))
        .then(|| {
            Mutex::new(Log {
                rows: Vec::with_capacity(LIMIT),
                lost: 0,
                next: 1,
            })
        })
    })
    .as_ref()
}
fn clock() -> i64 {
    let mut value = 0;
    unsafe {
        QueryPerformanceCounter(&mut value);
    }
    value
}

pub struct Span {
    id: u64,
    parent: u64,
    stage: &'static str,
    value: i64,
    call_start: i64,
    call_end: i64,
    hwnd: i64,
    _thread: PhantomData<Rc<()>>,
}
/// Bracket the actual API instruction inside the scope and keep its unmodified result.
pub fn native<T>(
    stage: &'static str,
    arg: i64,
    hwnd: i64,
    call: impl FnOnce() -> T,
    value: impl FnOnce(&T) -> i64,
) -> T {
    let mut span = span(stage, arg);
    if span.id == 0 {
        return call();
    }
    span.hwnd = hwnd;
    span.call_start = clock();
    let result = call();
    span.call_end = clock();
    span.value = value(&result);
    result
}
fn row(id: u64, parent: u64, stage: &'static str, ending: bool, value: i64) -> Entry {
    let before = clock();
    let (status, switches, reasons, cycles) = PROFILE.with(Profile::sample);
    let after = clock();
    Entry {
        id,
        parent,
        stage,
        ending,
        thread: unsafe { GetCurrentThreadId() },
        before,
        after,
        status,
        switches,
        reasons,
        cycles,
        value,
        call_start: 0,
        call_end: 0,
        hwnd: 0,
    }
}
impl Log {
    fn push(&mut self, entry: Entry) {
        if self.rows.len() < LIMIT {
            self.rows.push(entry);
        } else {
            self.lost += 1;
        }
    }
}
pub fn span(stage: &'static str, value: i64) -> Span {
    let mut span = Span {
        id: 0,
        parent: 0,
        stage,
        value,
        call_start: 0,
        call_end: 0,
        hwnd: 0,
        _thread: PhantomData,
    };
    if let Some(log) = log() {
        let mut entry = row(0, PARENT.get(), stage, false, value);
        let mut log = log.lock().expect("frame measurement lock");
        entry.id = log.next;
        log.next += 1;
        span.id = entry.id;
        span.parent = entry.parent;
        PARENT.set(entry.id);
        log.push(entry);
        drop(log);
        span.call_start = clock();
    }
    span
}
impl Drop for Span {
    fn drop(&mut self) {
        if self.id != 0 {
            let call_end = if self.call_end == 0 {
                clock()
            } else {
                self.call_end
            };
            let mut end = row(self.id, self.parent, self.stage, true, self.value);
            end.call_start = self.call_start;
            end.call_end = call_end;
            end.hwnd = self.hwnd;
            PARENT.set(self.parent);
            log()
                .unwrap()
                .lock()
                .expect("frame measurement lock")
                .push(end);
        }
    }
}
pub fn finish() -> std::io::Result<()> {
    if let Some(log) = log() {
        let mut freq = 0;
        unsafe {
            QueryPerformanceFrequency(&mut freq);
        }
        let log = log.lock().expect("frame measurement lock");
        let mut out = BufWriter::new(std::io::stdout().lock());
        writeln!(
            out,
            "FRAME_BEGIN {} {} {} {}",
            std::process::id(),
            freq,
            log.rows.len(),
            log.lost
        )?;
        for r in &log.rows {
            writeln!(
                out,
                "FRAME {} {} {} {} {} {} {} {} {} {} {} {} {} {} {}",
                r.id,
                r.parent,
                r.stage,
                u8::from(r.ending),
                r.thread,
                r.before,
                r.after,
                r.status,
                r.switches,
                r.reasons,
                r.cycles,
                r.value,
                r.call_start,
                r.call_end,
                r.hwnd
            )?;
        }
        writeln!(out, "FRAME_END")?;
        out.flush()?;
    }
    Ok(())
}
