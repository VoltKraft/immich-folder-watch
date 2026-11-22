//! Couple a live, changing notification icon to its own version-four callback.

use super::*;
use std::fs;

// The observer and the receiver use this system-wide, boot-relative Windows clock.
// Importing this no-argument Kernel32 API keeps the reviewed Cargo feature set intact.
#[link(name = "kernel32")]
unsafe extern "system" {
    #[link_name = "GetTickCount64"]
    fn get_tick_count64() -> u64;
}

pub(super) fn uptime_millis() -> u64 {
    // The API has no preconditions or borrowed output.
    unsafe { get_tick_count64() }
}

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

struct Image(HICON);

impl Drop for Image {
    fn drop(&mut self) {
        // Only our non-shared resource handles enter Image.
        unsafe {
            let _ = DestroyIcon(self.0);
        }
    }
}

fn image(rgb: [u8; 3]) -> Result<Image> {
    // A 32-bpp RT_ICON resource, including the trailing 1-bpp AND bitmap.
    // CreateIconFromResourceEx requires DWORD-aligned storage.
    #[repr(align(4))]
    struct Resource([u8; 40 + 32 * 32 * 4 + 32 * 4]);
    let mut dib = Resource([0; 40 + 32 * 32 * 4 + 32 * 4]);
    for (offset, value) in [(0, 40u32), (4, 32), (8, 64)] {
        dib.0[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
    }
    dib.0[12..14].copy_from_slice(&1u16.to_le_bytes());
    dib.0[14..16].copy_from_slice(&32u16.to_le_bytes());
    let frames: &[u8; 32656] = include_bytes!("../../gui/src/tray-icon.argb");
    let start = (16 * 16 + 22 * 22) * 4;
    for y in 0..32 {
        for x in 0..32 {
            let pixel = start + 4 * (y * 32 + x);
            let [a, r, g, b] = [
                frames[pixel],
                frames[pixel + 1],
                frames[pixel + 2],
                frames[pixel + 3],
            ];
            let value = if (5..27).contains(&x) && (5..27).contains(&y) {
                [rgb[2], rgb[1], rgb[0], 255]
            } else {
                [b, g, r, a]
            };
            let bottom_up = 40 + 4 * ((31 - y) * 32 + x);
            dib.0[bottom_up..bottom_up + 4].copy_from_slice(&value);
        }
    }
    // The API consumes the complete aligned resource synchronously and returns a new HICON.
    unsafe { CreateIconFromResourceEx(&dib.0, true, 0x30000, 32, 32, IMAGE_FLAGS(0)).map(Image) }
}

fn color(id: &str) -> Result<[u8; 3]> {
    let n = u32::from_str_radix(&id[..6], 16).map_err(|_| invalid())?;
    Ok([
        24 + ((n >> 16) & 63) as u8,
        164 + ((n >> 8) & 63) as u8,
        48 + (n & 63) as u8,
    ])
}

fn publish(area: &Path, stage: &str, info: String) -> Result<()> {
    let pending = area.join(format!("{stage}.pending"));
    fs::write(&pending, info)?;
    fs::rename(pending, area.join(stage))?;
    Ok(())
}

fn snapshot(area: &Path, stage: &str, icon: &Icon<'_>, ready: bool) -> Result<()> {
    let key = NOTIFYICONIDENTIFIER {
        cbSize: size_of::<NOTIFYICONIDENTIFIER>() as u32,
        hWnd: icon.owner.hwnd,
        uID: ICON,
        ..Default::default()
    };
    let (hr, rect) = match unsafe { Shell_NotifyIconGetRect(&key) } {
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
