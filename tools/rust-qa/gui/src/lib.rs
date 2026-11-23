//! Windows adapters used by the isolated native desktop fixture.
#![cfg(windows)]

mod launcher_delivery;
mod win32_instance;
mod windows_launcher;
pub use windows_launcher::{Launch, start_launcher};
mod windows_tray;
mod windows_tray_shell;
mod windows_tray_state;
pub use windows_tray::{NativeTray, TrayRequest};
pub use windows_tray_state::TrayEvent;

use std::ffi::c_void;
use std::ptr::null_mut;
use winit::raw_window_handle::{HasWindowHandle, RawWindowHandle};

type Handle = *mut c_void;

/// Request foreground for the visible root on its creating UI thread after explicit activation.
pub fn focus_owned_window(root: &winit::window::Window) {
    use windows::Win32::Foundation::HWND;
    use windows::Win32::UI::WindowsAndMessaging::{
        GA_ROOT, GetAncestor, IsWindowVisible, SetForegroundWindow,
    };

    let Ok(borrowed) = root.window_handle() else {
        return;
    };
    let RawWindowHandle::Win32(window) = borrowed.as_raw() else {
        return;
    };
    let hwnd = HWND(window.hwnd.get() as Handle);
    let mut pid = 0;
    // The borrow keeps the root alive. Query and activate it only on its own UI thread.
    unsafe {
        if GetWindowThreadProcessId(hwnd.0, &mut pid) != GetCurrentThreadId()
            || pid != std::process::id()
            || GetAncestor(hwnd, GA_ROOT) != hwnd
            || !IsWindowVisible(hwnd).as_bool()
        {
            return;
        }
        if root.is_minimized() == Some(true) {
            root.set_minimized(false);
        }
        let accepted = SetForegroundWindow(hwnd).as_bool();
        if std::env::var_os("IFW_QA_WINDOWS_LAUNCHER").is_some() {
            println!(
                "WINDOW_FOREGROUND_REQUEST pid={pid} hwnd={} accepted={accepted}",
                window.hwnd
            );
        }
    }
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetCurrentThreadId() -> u32;
}
#[link(name = "user32")]
unsafe extern "system" {
    fn GetWindowThreadProcessId(hwnd: Handle, pid: *mut u32) -> u32;
    fn GetFocus() -> Handle;
    fn GetForegroundWindow() -> Handle;
    fn GetKeyboardLayout(thread: u32) -> Handle;
}
#[link(name = "imm32")]
unsafe extern "system" {
    fn ImmGetContext(hwnd: Handle) -> Handle;
    fn ImmGetOpenStatus(context: Handle) -> i32;
    fn ImmGetConversionStatus(context: Handle, conversion: *mut u32, sentence: *mut u32) -> i32;
    fn ImmReleaseContext(hwnd: Handle, context: Handle) -> i32;
}

/// Called once per explicit private-pipe request, immediately after drawing the normal filename.
pub fn report_filename_mode(frame: &eframe::Frame, sample: u8, focused: bool, ime_requested: bool) {
    if !focused {
        println!("IME_MODE sample={sample} state=field-unfocused");
        return;
    }
    let Ok(handle) = frame.window_handle() else {
        println!("IME_MODE sample={sample} state=no-window");
        return;
    };
    let RawWindowHandle::Win32(window) = handle.as_raw() else {
        println!("IME_MODE sample={sample} state=no-window");
        return;
    };
    let hwnd = window.hwnd.get() as Handle;
    let mut pid = 0;
    // The frame lends its live HWND for this callback. The only writable argument
    // is the local PID. GetFocus refers to the calling UI thread's message queue.
    let (thread, owned_focus) = unsafe {
        let thread = GetCurrentThreadId();
        let owned = GetWindowThreadProcessId(hwnd, &mut pid) == thread
            && pid == std::process::id()
            && GetFocus() == hwnd
            && GetForegroundWindow() == hwnd;
        (thread, owned)
    };
    if !owned_focus {
        println!("IME_MODE sample={sample} state=no-owned-focus");
        return;
    }
    // Zero requests the calling thread's HKL. IMM receives only the verified
    // HWND on its creating UI thread. Context ownership stays with Windows.
    let layout = unsafe { GetKeyboardLayout(0) } as usize;
    let identity = format!("thread={thread} hkl={layout} imeRequested={ime_requested}");
    // Holding the frame's handle and executing synchronously preserves that ownership.
    let context = unsafe { ImmGetContext(hwnd) };
    if context.is_null() {
        println!("IME_MODE sample={sample} state=no-context {identity}");
        return;
    }
    // Some IMEs leave unsupported outputs untouched. Zero is a real alphanumeric mode.
    let mut flags = u32::MAX;
    // Read into a live DWORD, omit the optional sentence mode, then release
    // the borrowed HIMC to the same HWND without leaving this thread.
    let (open, reported, released) = unsafe {
        let open = ImmGetOpenStatus(context) != 0;
        let reported = ImmGetConversionStatus(context, &mut flags, null_mut()) != 0;
        (open, reported, ImmReleaseContext(hwnd, context) != 0)
    };
    if !released {
        println!("IME_MODE sample={sample} state=release-failed {identity}");
        return;
    }
    if reported && flags != u32::MAX {
        println!(
            "IME_MODE sample={sample} state=observed {identity} open={open} conversion={flags}"
        );
    } else {
        println!(
            "IME_MODE sample={sample} state=observed {identity} open={open} conversion=unavailable"
        );
    }
}
