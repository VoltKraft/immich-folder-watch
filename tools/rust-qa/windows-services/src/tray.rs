use std::ffi::OsStr;
use std::path::Path;
use std::time::{Duration, Instant};
use windows::Win32::Foundation::*;
use windows::Win32::System::RemoteDesktop::ProcessIdToSessionId;
use windows::Win32::System::StationsAndDesktops::*;
use windows::Win32::System::Threading::{
    GetCurrentProcessId, GetCurrentThreadId, GetProcessTimes, OpenProcess,
    PROCESS_QUERY_LIMITED_INFORMATION,
};
use windows::Win32::UI::Shell::*;
use windows::Win32::UI::WindowsAndMessaging::*;
use windows::core::{Owned, PCWSTR, Result, w};

use crate::{invalid, wide};

#[path = "tray_activation.rs"]
pub(super) mod activation;

#[path = "../../gui/src/windows_tray_shell.rs"]
mod shell;
use shell::*;

impl Icon<'_> {
    fn add(&mut self, phase: &str) -> Result<bool> {
        // LoadIconW returns a shared system icon. Do not destroy the shared handle.
        let shared = unsafe { LoadIconW(None, IDI_APPLICATION)? };
        Ok(self.register(phase, shared).0)
    }
}

fn taskbar_creation(hwnd: HWND, pid: u32, tid: u32) -> Option<u64> {
    unsafe {
        let process = Owned::new(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid).ok()?);
        let mut times = [FILETIME::default(); 4];
        let [created, exit, kernel, user] = &mut times;
        GetProcessTimes(*process, created, exit, kernel, user).ok()?;
        let mut owner = 0;
        (exit.dwLowDateTime == 0
            && exit.dwHighDateTime == 0
            && FindWindowW(w!("Shell_TrayWnd"), None).ok() == Some(hwnd)
            && GetWindowThreadProcessId(hwnd, Some(&mut owner)) == tid
            && owner == pid)
            .then_some((u64::from(created.dwHighDateTime) << 32) | u64::from(created.dwLowDateTime))
    }
}

fn host(prefix: &str) -> bool {
    unsafe {
        let bar = FindWindowW(w!("Shell_TrayWnd"), None).ok();
        let shell = GetShellWindow();
        let mut session = 0;
        let session_result = ProcessIdToSessionId(GetCurrentProcessId(), &mut session);
        if session_result.is_ok() {
            println!("{prefix}.session={session}");
        }
        // Read flags of the process's existing window station, without opening
        // or changing the interactive input desktop.
        let mut flags = USEROBJECTFLAGS::default();
        let station = GetProcessWindowStation().and_then(|handle| {
            GetUserObjectInformationW(
                HANDLE(handle.0),
                UOI_FLAGS,
                Some(std::ptr::from_mut(&mut flags).cast()),
                size_of::<USEROBJECTFLAGS>() as u32,
                None,
            )
        });
        match station {
            Ok(()) => println!(
                "{prefix}.station_visible={}",
                flags.dwFlags & WSF_VISIBLE as u32 != 0
            ),
            Err(e) => println!("{prefix}.station_flags_hresult={}", e.code().0),
        }
        if let Some(bar) = bar {
            let mut pid = 0;
            let tid = GetWindowThreadProcessId(bar, Some(&mut pid));
            if let Some(created) = taskbar_creation(bar, pid, tid) {
                println!("{prefix}.taskbar_creation={created}");
            }
            let mut host_session = 0;
            if ProcessIdToSessionId(pid, &mut host_session).is_ok() {
                println!("{prefix}.taskbar_session={host_session}");
            }
            println!(
                "{prefix}.taskbar_hwnd={}\n{prefix}.taskbar_tid={tid}",
                bar.0 as usize
            );
            if let Ok(name) = activation::desktop_name(tid) {
                println!("{prefix}.taskbar_desktop={name}");
            }
            println!(
                "{prefix}.taskbar_pid={pid}\n{prefix}.taskbar_visible={}",
                IsWindowVisible(bar).as_bool()
            );
        }
        if let Ok(name) = activation::desktop_name(GetCurrentThreadId()) {
            println!("{prefix}.thread_desktop={name}");
        }
        if !shell.is_invalid() {
            let mut pid = 0;
            let tid = GetWindowThreadProcessId(shell, Some(&mut pid));
            println!(
                "{prefix}.shell_hwnd={}\n{prefix}.shell_pid={pid}\n{prefix}.shell_tid={tid}",
                shell.0 as usize
            );
        }
        println!(
            "{prefix}.taskbar_present={}\n{prefix}.shell_window={}",
            bar.is_some(),
            !shell.is_invalid()
        );
        bar.is_some()
    }
}

fn pump(millis: u32) {
    pump_messages(millis, 256);
}

fn report_events(e: Events) {
    for (name, count) in [
        ("taskbar_created", e.taskbar),
        ("synthetic_taskbar_created", e.synthetic_taskbar),
        ("synthetic_open", e.synthetic_open),
        ("shell_open", e.shell_open),
        ("shell_context", e.shell_context),
        ("balloon_show", e.shown),
        ("balloon_hide", e.hidden),
        ("balloon_timeout", e.timed_out),
        ("balloon_click", e.clicked),
    ] {
        println!("tray.callbacks.{name}={count}");
    }
}

fn notification_state(prefix: &str) {
    match unsafe { SHQueryUserNotificationState() } {
        Ok(s) => println!("{prefix}.notification_state={}", s.0),
        Err(e) => println!("{prefix}.notification_state_hresult={}", e.code().0),
    }
}

fn request_notification(icon: &Icon<'_>, id: &str, body: &str) -> bool {
    let mut notice = icon.base();
    notice.uFlags = NIF_INFO | NIF_REALTIME;
    notice.dwInfoFlags = NIIF_INFO | NIIF_RESPECT_QUIET_TIME | NIIF_NOSOUND;
    copy_text(&mut notice.szInfoTitle, &format!("IFW notice {id}"));
    copy_text(&mut notice.szInfo, body);
    icon.call("notification_request", NIM_MODIFY, &notice)
}

fn signal_observer(area: &Path, name: &str, id: &str) -> Result<()> {
    let pending = area.join(format!("{name}.pending"));
    std::fs::write(&pending, id)?;
    std::fs::rename(pending, area.join(name))?;
    Ok(())
}

/// Issue one silent notification on the original disposable desktop after the observer is armed.
pub(super) fn notification_only(area: &Path, id: &str) -> Result<()> {
    let mut receiver = Receiver::new()?;
    host("notice");
    println!(
        "notice.pid={}\nnotice.tid={}\nnotice.owner_hwnd={}\nnotice.icon_id={ICON}",
        std::process::id(),
        unsafe { GetCurrentThreadId() },
        receiver.hwnd.0 as usize
    );
    let mut icon = Icon {
        owner: &receiver,
        prefix: "notice",
        title: format!("IFW tray {id}"),
        cleanup: false,
    };
    let image = unsafe { LoadIconW(None, IDI_APPLICATION)? };
    let (added, v4) = icon.register("initial", image);
    let trial = (|| {
        signal_observer(area, "notice.ready", id)?;
        let start = Instant::now();
        while !area.join("notice.go").is_file() {
            if area.join("notice.finish").is_file() || start.elapsed() >= Duration::from_secs(25) {
                return Err(invalid());
            }
            pump(30);
        }
        pump(0);
        let before = EVENTS.get();
        notification_state("notice");
        let requested = added
            && v4
            && request_notification(&icon, id, &format!("Synthetic IFW notification {id}"));
        println!("notice.requested={requested}");
        signal_observer(area, "notice.sent", id)?;
        let issued = Instant::now();
        loop {
            pump(40);
            if area.join("notice.finish").is_file()
                && (!requested
                    || EVENTS.get().shown > before.shown
                    || issued.elapsed() >= Duration::from_secs(8))
            {
                break;
            }
            if issued.elapsed() >= Duration::from_secs(25) {
                return Err(invalid());
            }
        }
        let after = EVENTS.get();
        host("notice_after");
        println!(
            "notice.balloon_show={}\nnotice.balloon_hide={}\nnotice.balloon_timeout={}\nnotice.balloon_click={}\nnotice.taskbar_created={}",
            after.shown.saturating_sub(before.shown),
            after.hidden.saturating_sub(before.hidden),
            after.timed_out.saturating_sub(before.timed_out),
            after.clicked.saturating_sub(before.clicked),
            after.taskbar.saturating_sub(before.taskbar)
        );
        Ok(())
    })();
    let removed = added && icon.remove("remove");
    drop(icon);
    let close = receiver.close();
    println!("notice.receiver_closed={}", close.is_ok());
    trial?;
    close?;
    if added && !removed {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn assess(area: &Path, id: &str) -> Result<()> {
    let receiver = Receiver::new()?;
    host("tray");
    println!(
        "tray.hidden_hwnd={}",
        !unsafe { IsWindowVisible(receiver.hwnd) }.as_bool()
    );
    let mut icon = Icon {
        owner: &receiver,
        prefix: "tray",
        title: format!("IFW tray {id}"),
        cleanup: false,
    };
    let first = icon.add("initial")?;
    println!(
        "tray.owner_hwnd={}\ntray.icon_id={ICON}",
        receiver.hwnd.0 as usize
    );
    let mut state = icon.base();
    state.uFlags = NIF_TIP | NIF_SHOWTIP;
    copy_text(&mut state.szTip, &icon.title);
    icon.call("modify", NIM_MODIFY, &state);
    match icon.rect() {
        Ok(rect) => {
            println!(
                "tray.icon_rect_nonempty={}",
                rect.right > rect.left && rect.bottom > rect.top
            );
            println!(
                "tray.rect_left={}\ntray.rect_top={}\ntray.rect_right={}\ntray.rect_bottom={}",
                rect.left, rect.top, rect.right, rect.bottom
            );
        }
        Err(e) => println!("tray.icon_rect_hresult={}", e.code().0),
    }
    notification_state("tray");
    request_notification(&icon, id, "Synthetic Windows notification assessment");
    std::fs::write(
        area.join("tray.ready"),
        if first { "registered" } else { "unavailable" },
    )?;
    let until = Instant::now() + Duration::from_secs(75);
    let mut handled = 0;
    while !area.join("tray.observed").is_file() {
        if Instant::now() >= until {
            return Err(invalid());
        }
        pump(50);
        let arrivals = EVENTS.get().taskbar;
        if arrivals > handled {
            icon.add("shell_taskbar_readd")?;
            handled = arrivals;
        }
    }
    // Model loss of this single icon without affecting Explorer or anyone's
    // taskbar. Route the registered message to this HWND only, with a marker.
    if first {
        icon.remove("controlled_remove");
    }
    unsafe {
        PostMessageW(
            Some(receiver.hwnd),
            REGISTERED.get(),
            WPARAM(SYNTHETIC_TASKBAR),
            LPARAM(0),
        )?;
        PostMessageW(Some(receiver.hwnd), SYNTHETIC_OPEN, WPARAM(0), LPARAM(0))?;
    }
    let until = Instant::now() + Duration::from_secs(2);
    let mut reapplied = false;
    while Instant::now() < until {
        pump(50);
        let events = EVENTS.get();
        if events.taskbar > handled {
            icon.add("shell_taskbar_readd")?;
            handled = events.taskbar;
        }
        if events.synthetic_taskbar != 0 && !reapplied {
            icon.add("synthetic_taskbar_readd")?;
            reapplied = true;
        }
        if reapplied && events.synthetic_open != 0 {
            break;
        }
    }
    report_events(EVENTS.get());
    icon.remove("remove");
    Ok(())
}

pub(super) fn empty_desktop(id: &str) -> Result<()> {
    let name = wide(OsStr::new(&format!("IFW-RW02-{id}")));
    // Never switch the user's input desktop. Only this fresh worker thread
    // joins the privately named desktop. Window destruction precedes restoring
    // its original borrowed desktop and closing the newly owned handle.
    unsafe {
        let original = GetThreadDesktop(GetCurrentThreadId())?;
        let desktop = CreateDesktopW(
            PCWSTR(name.as_ptr()),
            None,
            None,
            DESKTOP_CONTROL_FLAGS(0),
            DESKTOP_CREATEWINDOW.0 | DESKTOP_READOBJECTS.0 | DESKTOP_WRITEOBJECTS.0,
            None,
        )?;
        if let Err(e) = SetThreadDesktop(desktop) {
            let _ = CloseDesktop(desktop);
            return Err(e);
        }
        let result = (|| {
            host("empty");
            let receiver = Receiver::new()?;
            let mut icon = Icon {
                owner: &receiver,
                prefix: "empty",
                title: format!("IFW private {id}"),
                cleanup: false,
            };
            let available = icon.add("initial")?;
            println!("empty.fallback_required={}", !available);
            if available {
                icon.remove("remove");
            } else {
                // Only this non-input desktop sees the actual fallback window.
                // No user's window receives focus and no desktop is switched.
                SetWindowPos(
                    receiver.hwnd,
                    None,
                    20,
                    20,
                    240,
                    80,
                    SWP_NOACTIVATE | SWP_NOZORDER,
                )?;
                let _ = ShowWindow(receiver.hwnd, SW_SHOWNOACTIVATE);
                println!(
                    "empty.fallback_visible={}",
                    IsWindowVisible(receiver.hwnd).as_bool()
                );
                let _ = ShowWindow(receiver.hwnd, SW_HIDE);
            }
            Ok(())
        })();
        let restored = SetThreadDesktop(original);
        let closed = CloseDesktop(desktop);
        result.and(restored).and(closed)
    }
}
