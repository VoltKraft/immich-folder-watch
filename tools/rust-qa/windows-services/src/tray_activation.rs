//! Couple a live, changing notification icon to its own version-four callback.

use super::*;
use std::fs;

pub(super) fn desktop_name(tid: u32) -> Result<String> {
    let mut units = [0u16; 256];
    let mut count = 0u32;
    // The desktop returned by GetThreadDesktop is borrowed from this thread.
    unsafe {
        let desktop = GetThreadDesktop(tid)?;
        GetUserObjectInformationW(
            HANDLE(desktop.0),
            UOI_NAME,
            Some(units.as_mut_ptr().cast()),
            size_of_val(&units) as u32,
            Some(&mut count),
        )?;
    }
    let end = units
        .iter()
        .position(|&unit| unit == 0)
        .ok_or_else(invalid)?;
    String::from_utf16(&units[..end]).map_err(|_| invalid())
}

fn publish(area: &Path, stage: &str, info: String) -> Result<()> {
    let pending = area.join(format!("{stage}.pending"));
    fs::write(&pending, info)?;
    fs::rename(pending, area.join(stage))?;
    Ok(())
}

fn snapshot(area: &Path, stage: &str, icon: &Icon<'_>, ready: bool) -> Result<()> {
    let (hr, rect) = match icon.rect() {
        Ok(rect) => (0, rect),
        Err(e) => (e.code().0, RECT::default()),
    };
    let e = EVENTS.get();
    publish(
        area,
        stage,
        format!(
            "{} {} {ICON} {} {hr} {} {} {} {} {}",
            unsafe { GetCurrentProcessId() },
            icon.owner.hwnd.0 as usize,
            u8::from(ready),
            rect.left,
            rect.top,
            rect.right,
            rect.bottom,
            e.pointer_open
        ),
    )
}

fn requested(area: &Path, name: &str, until: Instant) -> Result<bool> {
    loop {
        pump(20);
        if area.join("finish").is_file() {
            return Ok(false);
        }
        if area.join(name).is_file() {
            return Ok(true);
        }
        if Instant::now() >= until {
            return Err(invalid());
        }
    }
}

fn private_taskbar(desktop: &str) -> Result<Option<(HWND, u32, u32)>> {
    // Only inspect the visible Shell window on the current synthetic desktop.
    unsafe {
        let Ok(bar) = FindWindowW(w!("Shell_TrayWnd"), None) else {
            return Ok(None);
        };
        let mut pid = 0;
        let thread = GetWindowThreadProcessId(bar, Some(&mut pid));
        if thread == 0
            || pid == 0
            || !IsWindowVisible(bar).as_bool()
            || desktop_name(thread)? != desktop
        {
            return Ok(None);
        }
        Ok(Some((bar, pid, thread)))
    }
}

fn register_on_startup(
    icon: &mut Icon<'_>,
    image: HICON,
    area: &Path,
    desktop: &str,
) -> Result<(bool, bool)> {
    let original = private_taskbar(desktop)?;
    let initial = icon.register("initial", image);
    if initial.0 {
        return Ok(initial);
    }
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(3)
        && EVENTS.get().taskbar == 0
        && !area.join("finish").is_file()
    {
        pump(50);
    }
    let same = original.is_some() && original == private_taskbar(desktop)?;
    println!(
        "private_tray.startup_wait_ms={}",
        start.elapsed().as_millis()
    );
    println!("private_tray.startup_broadcasts={}", EVENTS.get().taskbar);
    println!("private_tray.startup_host_unchanged={same}");
    if same && !area.join("finish").is_file() {
        return Ok(icon.register("startup_retry", image));
    }
    Ok(initial)
}

pub(crate) fn assess(area: &Path, id: &str) -> Result<()> {
    let desktop = format!("IfwQa_{id}");
    if desktop_name(unsafe { GetCurrentThreadId() })? != desktop {
        return Err(invalid());
    }
    // Both observers operate on the primary desktop's physical screen coordinates.
    unsafe {
        let _ = SetProcessDPIAware();
        if !IsProcessDPIAware().as_bool() {
            return Err(invalid());
        }
    }
    // Retain the two image handles until after the registered icon has been deleted.
    let rgb = color(id)?;
    let first = image(rgb)?;
    let second = image(rgb.map(|channel| 255 - channel))?;
    let receiver = Receiver::new()?;
    host("private_tray");
    let mut icon = Icon {
        owner: &receiver,
        prefix: "private_tray",
        title: format!("IFW tray {id}"),
        cleanup: false,
    };
    let (added, version4) = register_on_startup(&mut icon, first.0, area, &desktop)?;
    println!("private_tray.registered={added}");
    snapshot(area, "first", &icon, added && version4)?;
    let until = Instant::now() + Duration::from_secs(100);
    if added && version4 && requested(area, "change", until)? {
        let mut update = icon.base();
        update.uFlags = NIF_ICON;
        update.hIcon = second.0;
        let modified = icon.call("change", NIM_MODIFY, &update);
        snapshot(area, "second", &icon, modified)?;
        if modified && requested(area, "arm", until)? {
            snapshot(area, "armed", &icon, true)?;
            while Instant::now() < until && !area.join("finish").is_file() {
                pump(10);
                let e = EVENTS.get();
                if e.pointer_open > 0 {
                    publish(
                        area,
                        "callback",
                        format!(
                            "{} {} {} {} {} {} {}",
                            e.pointer_open,
                            e.last_pointer_code,
                            e.last_pointer_id,
                            e.last_queued_tick.map_or(-1, i64::from),
                            e.pointer_up,
                            e.last_dispatch_tick,
                            e.last_pointer_tick
                        ),
                    )?;
                    break;
                }
            }
            // Keep the icon and receiver stable until the outside observer read the event.
            if !area.join("finish").is_file() {
                requested(area, "finish", until)?;
            }
        }
    }
    let events = EVENTS.get();
    println!(
        "private_tray.pointer_up={}\nprivate_tray.pointer_open={}\nprivate_tray.synthetic_open={}",
        events.pointer_up, events.pointer_open, events.synthetic_open
    );
    if added && !icon.remove("remove") {
        return Err(invalid());
    }
    Ok(())
}
