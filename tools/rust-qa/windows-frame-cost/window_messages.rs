//! Record synchronous calls on the GUI thread only while its retained root is in ShowWindow.
use std::cell::{Cell, RefCell};
use std::io::{self, Write};
use std::marker::PhantomData;
use std::rc::Rc;

// This fixed allocation includes one marker per ShowWindow, including shows with no callbacks.
const LIMIT: usize = 65_536;
thread_local! {
    pub(super) static ROOT: Cell<i64> = const { Cell::new(0) };
    static ACTIVE: Cell<(i64, usize)> = const { Cell::new((0, 0)) };
    static EVENTS: RefCell<Events> = const { RefCell::new(Events { rows: Vec::new(), lost: 0 }) };
}
struct Entry {
    parent: usize,
    value: u64,
    stage: &'static str,
    start: i64,
    end: i64,
}
struct Events {
    rows: Vec<Entry>,
    lost: usize,
}
pub struct Scope {
    index: usize,
    previous: (i64, usize),
    _thread: PhantomData<Rc<()>>,
}
impl Scope {
    fn enter(hwnd: i64, parent: usize, stage: &'static str, value: u64) -> Option<Self> {
        let index = EVENTS.with_borrow_mut(|events| {
            if events.rows.len() == LIMIT {
                events.lost = events.lost.saturating_add(1);
                return None;
            }
            if events.rows.capacity() == 0 {
                events.rows.reserve_exact(LIMIT);
            }
            events.rows.push(Entry {
                parent,
                value,
                stage,
                start: 0,
                end: 0,
            });
            Some(events.rows.len())
        })?;
        let previous = ACTIVE.replace((hwnd, index));
        EVENTS.with_borrow_mut(|events| events.rows[index - 1].start = super::clock());
        Some(Self {
            index,
            previous,
            _thread: PhantomData,
        })
    }
}
impl Drop for Scope {
    fn drop(&mut self) {
        let end = super::clock();
        ACTIVE.set(self.previous);
        EVENTS.with_borrow_mut(|events| events.rows[self.index - 1].end = end);
    }
}

pub(super) fn show(hwnd: i64, native_id: u64) -> Option<Scope> {
    (hwnd != 0 && hwnd == ROOT.get())
        .then(|| Scope::enter(hwnd, 0, "show", native_id))
        .flatten()
}

fn message(hwnd: i64, msg: u32, stage: &'static str) -> Option<Scope> {
    let (owner, parent) = ACTIVE.get();
    if parent == 0 || hwnd != owner {
        return None;
    }
    // Collapse all WM_USER and higher numbers into one category. Never record parameters.
    Scope::enter(hwnd, parent, stage, u64::from(msg.min(0x400)))
}
pub fn wndproc(hwnd: i64, msg: u32) -> Option<Scope> {
    message(hwnd, msg, "wndproc")
}
pub fn default_proc(hwnd: i64, msg: u32) -> Option<Scope> {
    message(hwnd, msg, "default")
}

pub(super) fn write(out: &mut impl Write, frequency: i64) -> io::Result<()> {
    EVENTS.with_borrow(|events| {
        writeln!(
            out,
            "WND_BEGIN 1 {} {} {frequency} {} {}",
            std::process::id(),
            unsafe { super::GetCurrentThreadId() },
            events.rows.len(),
            events.lost
        )?;
        for (i, entry) in events.rows.iter().enumerate() {
            writeln!(
                out,
                "WND {} {} {} {} {} {}",
                i + 1,
                entry.parent,
                entry.stage,
                entry.value,
                entry.start,
                entry.end
            )?;
        }
        writeln!(out, "WND_END")
    })
}
