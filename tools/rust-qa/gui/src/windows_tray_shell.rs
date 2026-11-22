//! Native notification-area receiver and icon shared by the GUI and its standalone Shell assessment.
use std::cell::Cell;
use windows::Win32::Foundation::*;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Shell::*;
use windows::Win32::UI::WindowsAndMessaging::*;
use windows::core::{Error, PCWSTR, Result, w};

// The observer and the receiver use this system-wide, boot-relative Windows clock.
// Importing this no-argument Kernel32 API keeps the reviewed Cargo feature set intact.
#[link(name = "kernel32")]
unsafe extern "system" {
    #[link_name = "GetTickCount64"]
    fn get_tick_count64() -> u64;
}

fn uptime_millis() -> u64 {
    // The API has no preconditions or borrowed output.
    unsafe { get_tick_count64() }
}

const CALLBACK: u32 = WM_APP + 23;
pub(crate) const SYNTHETIC_OPEN: u32 = WM_APP + 24;
pub(crate) const SYNTHETIC_TASKBAR: usize = 0x1f02;
pub(crate) const ICON: u32 = 23;

#[derive(Default, Clone, Copy)]
pub(crate) struct OpenEvent {
    pub(crate) ordinal: u32,
    pub(crate) code: u32,
    pub(crate) queued_ms: Option<u32>,
    pub(crate) dispatch_ms: u64,
}

#[derive(Default, Clone, Copy)]
pub(crate) struct Events {
    pub(crate) open: OpenEvent,
    pub(crate) taskbar: u32,
    pub(crate) synthetic_taskbar: u32,
    pub(crate) synthetic_open: u32,
    pub(crate) shell_open: u32,
    pub(crate) pointer_open: u32,
    pub(crate) last_pointer_code: u32,
    pub(crate) last_pointer_tick: u32,
    pub(crate) last_queued_tick: Option<u32>,
    pub(crate) last_dispatch_tick: u64,
    pub(crate) last_pointer_id: u32,
    pub(crate) pointer_up: u32,
    pub(crate) shell_context: u32,
    pub(crate) shown: u32,
    pub(crate) hidden: u32,
    pub(crate) timed_out: u32,
    pub(crate) clicked: u32,
}

thread_local! {
    pub(crate) static REGISTERED: Cell<u32> = const { Cell::new(0) };
    pub(crate) static EVENTS: Cell<Events> = Cell::new(Events::default());
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
            key if matches!(key, NIN_SELECT | WM_LBUTTONDBLCLK) || key == NIN_SELECT + 1 => {
                e.shell_open = e.shell_open.saturating_add(1);
                if id == ICON {
                    // A nonqueued sent callback has no MSG.time of its own. GetMessageTime alone
                    // can then describe the thread's previous, unrelated queue entry.
                    let queued_ms = DISPATCHING.get().and_then(|entry| {
                        (entry.hwnd == hwnd
                            && entry.message == msg
                            && entry.wParam == wp
                            && entry.lParam == lp
                            && unsafe { InSendMessageEx(None) } == ISMEX_NOSEND)
                            .then_some(entry.time)
                    });
                    e.open = OpenEvent {
                        ordinal: e.open.ordinal.saturating_add(1),
                        code,
                        queued_ms,
                        dispatch_ms: uptime_millis(),
                    };
                    if matches!(code, NIN_SELECT | WM_LBUTTONDBLCLK) {
                        e.pointer_open = e.pointer_open.saturating_add(1);
                        e.last_pointer_id = id;
                        e.last_pointer_code = e.open.code;
                        e.last_pointer_tick = unsafe { GetMessageTime() } as u32;
                        e.last_queued_tick = e.open.queued_ms;
                        e.last_dispatch_tick = e.open.dispatch_ms;
                    }
                }
            }
            WM_LBUTTONUP if id == ICON => e.pointer_up = e.pointer_up.saturating_add(1),
            WM_CONTEXTMENU | WM_RBUTTONUP => e.shell_context = e.shell_context.saturating_add(1),
            NIN_BALLOONSHOW if id == ICON => e.shown = e.shown.saturating_add(1),
            NIN_BALLOONHIDE if id == ICON => e.hidden = e.hidden.saturating_add(1),
            NIN_BALLOONTIMEOUT if id == ICON => e.timed_out = e.timed_out.saturating_add(1),
            NIN_BALLOONUSERCLICK if id == ICON => e.clicked = e.clicked.saturating_add(1),
            _ => {}
        }
    } else {
        // Pass through synchronous creation/destruction and ordinary OS messages.
        return unsafe { DefWindowProcW(hwnd, msg, wp, lp) };
    }
    EVENTS.set(e);
    LRESULT(0)
}

pub(crate) struct Receiver {
    pub(crate) hwnd: HWND,
    instance: HINSTANCE,
}
const CLASS: PCWSTR = w!("IFW RW02 synthetic tray receiver");

impl Receiver {
    pub(crate) fn new() -> Result<Self> {
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
    pub(crate) fn close(&mut self) -> Result<()> {
        // The registering thread releases the HWND before unregistering its window class.
        unsafe {
            if !self.hwnd.is_invalid() {
                DestroyWindow(self.hwnd)?;
                self.hwnd = HWND::default();
            }
            if !self.instance.is_invalid() {
                UnregisterClassW(CLASS, Some(self.instance))?;
                self.instance = HINSTANCE::default();
            }
        }
        Ok(())
    }
}

impl Drop for Receiver {
    fn drop(&mut self) {
        let _ = self.close();
    }
}

pub(crate) fn copy_text<const N: usize>(buffer: &mut [u16; N], text: &str) {
    for (out, unit) in buffer[..N - 1].iter_mut().zip(text.encode_utf16()) {
        *out = unit;
    }
}

pub(crate) struct Icon<'a> {
    pub(crate) owner: &'a Receiver,
    pub(crate) prefix: &'static str,
    pub(crate) title: String,
    pub(crate) cleanup: bool,
}

impl Icon<'_> {
    pub(crate) fn rect(&self) -> Result<RECT> {
        let key = NOTIFYICONIDENTIFIER {
            cbSize: size_of::<NOTIFYICONIDENTIFIER>() as u32,
            hWnd: self.owner.hwnd,
            uID: ICON,
            ..Default::default()
        };
        // The Shell only reads the identifier. The receiver outlives the icon.
        unsafe { Shell_NotifyIconGetRect(&key) }
    }

    pub(crate) fn base(&self) -> NOTIFYICONDATAW {
        NOTIFYICONDATAW {
            cbSize: size_of::<NOTIFYICONDATAW>() as u32,
            hWnd: self.owner.hwnd,
            uID: ICON,
            ..Default::default()
        }
    }

    pub(crate) fn call(&self, step: &str, op: NOTIFY_ICON_MESSAGE, data: &NOTIFYICONDATAW) -> bool {
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

    pub(crate) fn register(&mut self, phase: &str, image: HICON) -> (bool, bool) {
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

    pub(crate) fn remove(&mut self, phase: &str) -> bool {
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

pub(crate) fn pump_messages(millis: u32, limit: usize) {
    // Dispatch only messages for the current assessing thread. The outer
    // finite deadline also handles idle desktops.
    unsafe {
        MsgWaitForMultipleObjectsEx(None, millis, QS_ALLINPUT, MWMO_INPUTAVAILABLE);
        let mut msg = MSG::default();
        for _ in 0..limit {
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

pub(crate) struct Image(pub(crate) HICON);

impl Drop for Image {
    fn drop(&mut self) {
        // Only our non-shared resource handles enter Image.
        unsafe {
            let _ = DestroyIcon(self.0);
        }
    }
}

pub(crate) fn image(rgb: [u8; 3]) -> Result<Image> {
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
    let frames: &[u8; 32656] = include_bytes!("tray-icon.argb");
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

pub(crate) fn color(id: &str) -> Result<[u8; 3]> {
    let n = id
        .get(..6)
        .and_then(|head| u32::from_str_radix(head, 16).ok())
        .ok_or_else(|| Error::from_hresult(E_INVALIDARG))?;
    Ok([
        24 + ((n >> 16) & 63) as u8,
        164 + ((n >> 8) & 63) as u8,
        48 + (n & 63) as u8,
    ])
}

#[cfg(test)]
mod notification_tests {
    use super::*;

    #[test]
    fn balloon_callbacks_belong_to_the_registered_v4_icon() {
        let counts = || {
            let e = EVENTS.get();
            [e.shown, e.hidden, e.timed_out, e.clicked]
        };
        for (id, expected) in [(ICON + 1, [0; 4]), (ICON, [1; 4])] {
            for event in [
                NIN_BALLOONSHOW,
                NIN_BALLOONHIDE,
                NIN_BALLOONTIMEOUT,
                NIN_BALLOONUSERCLICK,
            ] {
                // The callback branch only decodes these scalar test parameters.
                unsafe {
                    window_proc(
                        HWND::default(),
                        CALLBACK,
                        WPARAM::default(),
                        LPARAM(((id << 16) | event) as isize),
                    )
                };
            }
            assert_eq!(counts(), expected);
        }
    }
}
