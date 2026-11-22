//! Call the same Windows bindings used by winit's event loop and desktop bounds.
#![no_std]

use windows_sys::Win32::System::Threading::GetCurrentThreadId;
use windows_sys::Win32::UI::WindowsAndMessaging::GetSystemMetrics;

#[unsafe(no_mangle)]
pub extern "system" fn ifw_current_thread_id() -> u32 {
    // The query returns the calling thread's ID and accepts no handles or pointers.
    unsafe { GetCurrentThreadId() }
}

#[unsafe(no_mangle)]
pub extern "system" fn ifw_system_metric(index: i32) -> i32 {
    // GetSystemMetrics accepts a numeric selector and writes no caller-owned memory.
    unsafe { GetSystemMetrics(index) }
}
