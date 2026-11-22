//! Record bounded native timing spans only in a separately requested diagnostic scan.
use native_gui_assessment::{counter, frequency, thread_id};
use std::io::{BufWriter, Write};
use std::sync::{Mutex, OnceLock};
use winit::event::WindowEvent;
use winit::raw_window_handle::{HasWindowHandle, RawWindowHandle};
use winit::window::Window;

const CAPACITY: usize = 65_536;
static TRACE: OnceLock<Option<Mutex<Log>>> = OnceLock::new();

#[derive(Clone, Copy)]
struct Entry {
    label: &'static str,
    thread: u32,
    start: i64,
    end: i64,
    hwnd: isize,
    before: i64,
    after: i64,
    sampled: i64,
}

struct Log {
    entries: Vec<Entry>,
    lost: usize,
}

fn log() -> Option<&'static Mutex<Log>> {
    TRACE
        .get_or_init(|| {
            (std::env::var("IFW_QA_ISOLATED").as_deref() == Ok("1")
                && std::env::var("IFW_QA_WINDOWS_DISPATCH").as_deref() == Ok("1"))
            .then(|| {
                Mutex::new(Log {
                    entries: Vec::with_capacity(CAPACITY),
                    lost: 0,
                })
            })
        })
        .as_ref()
}

pub(super) struct Span(Entry);

pub(super) fn span(label: &'static str) -> Option<Span> {
    log().map(|_| {
        Span(Entry {
            label,
            thread: thread_id(),
            start: counter(),
            end: 0,
            hwnd: 0,
            before: -1,
            after: -1,
            sampled: 0,
        })
    })
}

pub(super) fn event(event: &WindowEvent) -> Option<Span> {
    match event {
        WindowEvent::CloseRequested => span("close-event"),
        WindowEvent::RedrawRequested => span("redraw-event"),
        WindowEvent::Resized(size) => {
            let mut guard = span("resize-event")?;
            guard.0.before = i64::from(size.width);
            guard.0.after = i64::from(size.height);
            Some(guard)
        }
        WindowEvent::Focused(_) => span("focus-event"),
        WindowEvent::Occluded(_) => span("occlusion-event"),
        _ => span("window-event"),
    }
}

impl Drop for Span {
    fn drop(&mut self) {
        if self.0.end == 0 {
            self.0.end = counter();
        }
        let mut log = log().unwrap().lock().expect("dispatch trace lock poisoned");
        if log.entries.len() == CAPACITY {
            log.lost += 1;
        } else {
            log.entries.push(self.0);
        }
    }
}

pub(super) fn visibility(window: &Window, visible: bool) {
    let Some(mut guard) = span(if visible { "show" } else { "hide" }) else {
        window.set_visible(visible);
        return;
    };
    let entry = &mut guard.0;
    entry.hwnd = match window.window_handle().map(|handle| handle.as_raw()) {
        Ok(RawWindowHandle::Win32(handle)) => handle.hwnd.get(),
        _ => 0,
    };
    let actual = || window.is_visible().map_or(-1, i64::from);
    entry.before = actual();
    entry.start = counter();
    window.set_visible(visible);
    entry.end = counter();
    entry.after = actual();
    entry.sampled = counter();
}

pub(super) fn finish(single_wake: bool) -> std::io::Result<()> {
    if let Some(log) = log() {
        let log = log.lock().expect("dispatch trace lock poisoned");
        let mut output = BufWriter::new(std::io::stdout().lock());
        writeln!(
            output,
            "DISPATCH_BEGIN {} {} {} {} {}",
            std::process::id(),
            frequency(),
            usize::from(single_wake),
            log.entries.len(),
            log.lost
        )?;
        for e in &log.entries {
            writeln!(
                output,
                "DISPATCH {} {} {} {} {} {} {} {}",
                e.label, e.thread, e.start, e.end, e.hwnd, e.before, e.after, e.sampled
            )?;
        }
        writeln!(output, "DISPATCH_END")?;
        output.flush()?;
    }
    Ok(())
}
