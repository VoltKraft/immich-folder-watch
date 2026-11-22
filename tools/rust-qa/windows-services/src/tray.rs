use std::cell::Cell;
use std::ffi::OsStr;
use std::path::Path;
use std::time::{Duration, Instant};
use windows::Win32::Foundation::*;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::RemoteDesktop::ProcessIdToSessionId;
use windows::Win32::System::StationsAndDesktops::*;
use windows::Win32::System::Threading::{GetCurrentProcessId, GetCurrentThreadId};
use windows::Win32::UI::Shell::*;
use windows::Win32::UI::WindowsAndMessaging::*;
use windows::core::{Error, PCWSTR, Result, w};

use crate::{invalid, wide};

#[path = "tray_activation.rs"]
pub(super) mod activation;

const CALLBACK: u32 = WM_APP + 23;
const SYNTHETIC_OPEN: u32 = WM_APP + 24;
const SYNTHETIC_TASKBAR: usize = 0x1f02;
const ICON: u32 = 23;

#[derive(Default, Clone, Copy)]
struct Events {
    taskbar: u32,
    synthetic_taskbar: u32,
    synthetic_open: u32,
    shell_open: u32,
    pointer_open: u32,
    last_pointer_code: u32,
    last_pointer_tick: u32,
    last_queued_tick: Option<u32>,
    last_dispatch_tick: u64,
    last_pointer_id: u32,
    pointer_up: u32,
    shell_context: u32,
    shown: u32,
    hidden: u32,
    timed_out: u32,
    clicked: u32,
}

thread_local! {
    static REGISTERED: Cell<u32> = const { Cell::new(0) };
    static EVENTS: Cell<Events> = Cell::new(Events::default());
    static DISPATCHING: Cell<Option<MSG>> = const { Cell::new(None) };
}

unsafe extern "system" fn window_proc(hwnd: HWND, msg: u32, wp: WPARAM, lp: LPARAM) -> LRESULT {
    // The thread owns its hidden HWND and counters. No borrowed Rust references
    // or heap allocations cross the Win32 callback boundary.
    let mut e = EVENTS.get();
    if msg != 0 && msg == REGISTERED.get() {
        if wp.0 == SYNTHETIC_TASKBAR {
            e.synthetic_taskbar = e.synthetic_taskbar.saturating_add(1);
        } else {
            e.taskbar = e.taskbar.saturating_add(1);
        }
    } else if msg == SYNTHETIC_OPEN {
        e.synthetic_open = e.synthetic_open.saturating_add(1);
    } else if msg == CALLBACK {
        // Version 4 puts the notification code in LOWORD(lParam).
        let code = lp.0 as u32 & 0xffff;
        let id = (lp.0 as u32) >> 16;
        match code {
            NIN_SELECT | WM_LBUTTONDBLCLK => {
                e.shell_open = e.shell_open.saturating_add(1);
                if id == ICON {
                    e.pointer_open = e.pointer_open.saturating_add(1);
                    e.last_pointer_id = id;
                    e.last_pointer_code = code;
                    e.last_pointer_tick = unsafe { GetMessageTime() } as u32;
                    // A nonqueued sent callback has no MSG.time of its own. GetMessageTime alone
                    // can then describe the thread's previous, unrelated queue entry.
                    e.last_queued_tick = DISPATCHING.get().and_then(|entry| {
                        (entry.hwnd == hwnd
                            && entry.message == msg
                            && entry.wParam == wp
                            && entry.lParam == lp
                            && unsafe { InSendMessageEx(None) } == ISMEX_NOSEND)
                            .then_some(entry.time)
                    });
                    e.last_dispatch_tick = activation::uptime_millis();
                }
            }
            WM_LBUTTONUP if id == ICON => e.pointer_up = e.pointer_up.saturating_add(1),
            key if key == NIN_SELECT + 1 => e.shell_open = e.shell_open.saturating_add(1),
            WM_CONTEXTMENU | WM_RBUTTONUP => e.shell_context = e.shell_context.saturating_add(1),
            NIN_BALLOONSHOW => e.shown = e.shown.saturating_add(1),
            NIN_BALLOONHIDE => e.hidden = e.hidden.saturating_add(1),
            NIN_BALLOONTIMEOUT => e.timed_out = e.timed_out.saturating_add(1),
            NIN_BALLOONUSERCLICK => e.clicked = e.clicked.saturating_add(1),
            _ => {}
        }
    } else {
        // Pass through synchronous creation/destruction and ordinary OS messages.
        return unsafe { DefWindowProcW(hwnd, msg, wp, lp) };
    }
    EVENTS.set(e);
    LRESULT(0)
}

struct Receiver {
    hwnd: HWND,
    instance: HINSTANCE,
}
const CLASS: PCWSTR = w!("IFW RW02 synthetic tray receiver");

impl Receiver {
    fn new() -> Result<Self> {
        // A hidden top-level tool window receives TaskbarCreated broadcasts.
        // A message-only window cannot receive that broadcast.
        unsafe {
            let instance = HINSTANCE(GetModuleHandleW(None)?.0);
            let registered = RegisterWindowMessageW(w!("TaskbarCreated"));
            if registered == 0 {
                return Err(Error::from_thread());
            }
            REGISTERED.set(registered);
            EVENTS.set(Events::default());
            let class = WNDCLASSW {
                hInstance: instance,
                lpszClassName: CLASS,
                lpfnWndProc: Some(window_proc),
                ..Default::default()
            };
            if RegisterClassW(&class) == 0 {
                return Err(Error::from_thread());
            }
            match CreateWindowExW(
                WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                CLASS,
                CLASS,
                WS_POPUP,
                -20_000,
                -20_000,
                1,
                1,
                None,
                None,
                Some(instance),
                None,
            ) {
                Ok(hwnd) => Ok(Self { hwnd, instance }),
                Err(e) => {
                    let _ = UnregisterClassW(CLASS, Some(instance));
                    Err(e)
                }
            }
        }
    }
}

impl Drop for Receiver {
    fn drop(&mut self) {
        // Drop on the registering thread, after its icon guard.
        unsafe {
            let _ = DestroyWindow(self.hwnd);
            let _ = UnregisterClassW(CLASS, Some(self.instance));
        }
    }
}

fn copy_text<const N: usize>(buffer: &mut [u16; N], text: &str) {
    for (out, unit) in buffer[..N - 1].iter_mut().zip(text.encode_utf16()) {
        *out = unit;
    }
}

struct Icon<'a> {
    owner: &'a Receiver,
    prefix: &'static str,
    title: String,
    cleanup: bool,
}

impl Icon<'_> {
    fn base(&self) -> NOTIFYICONDATAW {
        NOTIFYICONDATAW {
            cbSize: size_of::<NOTIFYICONDATAW>() as u32,
            hWnd: self.owner.hwnd,
            uID: ICON,
            ..Default::default()
        }
    }

    fn call(&self, step: &str, op: NOTIFY_ICON_MESSAGE, data: &NOTIFYICONDATAW) -> bool {
        // Shell_NotifyIcon documents BOOL, without a reliable extended error
        // contract. Clear and retain raw last-error only as diagnostic context.
        let (ok, raw) = unsafe {
            SetLastError(WIN32_ERROR(0));
            let ok = Shell_NotifyIconW(op, data).as_bool();
            (ok, GetLastError().0)
        };
        println!(
            "{}.{}={}\n{}.{}.raw_last_error={}",
            self.prefix, step, ok, self.prefix, step, raw
        );
        ok
    }

    fn add(&mut self, phase: &str) -> Result<bool> {
        // LoadIconW returns a shared system icon. Do not destroy the shared handle.
        let shared = unsafe { LoadIconW(None, IDI_APPLICATION)? };
        Ok(self.register(phase, shared).0)
    }

    fn register(&mut self, phase: &str, image: HICON) -> (bool, bool) {
        let mut data = self.base();
        data.uFlags = NIF_MESSAGE | NIF_TIP | NIF_ICON | NIF_SHOWTIP;
        data.uCallbackMessage = CALLBACK;
        data.hIcon = image;
        copy_text(&mut data.szTip, &self.title);
        let added = self.call(&format!("{phase}.add"), NIM_ADD, &data);
        if added {
            self.cleanup = true;
            let mut version = self.base();
            version.Anonymous.uVersion = NOTIFYICON_VERSION_4;
            return (
                true,
                self.call(&format!("{phase}.version4"), NIM_SETVERSION, &version),
            );
        }
        (false, false)
    }

    fn remove(&mut self, phase: &str) -> bool {
        let result = self.call(phase, NIM_DELETE, &self.base());
        if result {
            self.cleanup = false;
        }
        result
    }
}

impl Drop for Icon<'_> {
    fn drop(&mut self) {
        if self.cleanup {
            self.remove("cleanup_retry");
        }
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
        println!(
            "{prefix}.taskbar_present={}\n{prefix}.shell_window={}",
            bar.is_some(),
            !shell.is_invalid()
        );
        bar.is_some()
    }
}

fn pump(millis: u32) {
    // Dispatch only messages for the current assessing thread. The outer
    // finite deadline also handles idle desktops.
    unsafe {
        MsgWaitForMultipleObjectsEx(None, millis, QS_ALLINPUT, MWMO_INPUTAVAILABLE);
        let mut msg = MSG::default();
        for _ in 0..256 {
            if !PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).as_bool() {
                break;
            }
            let _ = TranslateMessage(&msg);
            let previous = DISPATCHING.replace((msg.message == CALLBACK).then_some(msg));
            DispatchMessageW(&msg);
            DISPATCHING.set(previous);
        }
    }
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
    let key = NOTIFYICONIDENTIFIER {
        cbSize: size_of::<NOTIFYICONIDENTIFIER>() as u32,
        hWnd: receiver.hwnd,
        uID: ICON,
        ..Default::default()
    };
    match unsafe { Shell_NotifyIconGetRect(&key) } {
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
    match unsafe { SHQueryUserNotificationState() } {
        Ok(s) => println!("tray.notification_state={}", s.0),
        Err(e) => println!("tray.notification_state_hresult={}", e.code().0),
    }
    let mut notice = icon.base();
    notice.uFlags = NIF_INFO | NIF_REALTIME;
    notice.dwInfoFlags = NIIF_INFO | NIIF_RESPECT_QUIET_TIME | NIIF_NOSOUND;
    copy_text(&mut notice.szInfoTitle, &format!("IFW notice {id}"));
    copy_text(
        &mut notice.szInfo,
        "Synthetic Windows notification assessment",
    );
    icon.call("notification_request", NIM_MODIFY, &notice);
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
