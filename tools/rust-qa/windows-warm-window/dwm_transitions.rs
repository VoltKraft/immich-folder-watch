//! Apply the diagnostic DWM policy only to the caller's original root window.
pub fn observe_transitions(window: &winit::window::Window, mode: &std::ffi::OsStr) {
    use crate::{GetWindowThreadProcessId, Handle};
    use windows::Win32::Foundation::HWND;
    use windows::Win32::UI::WindowsAndMessaging::{GA_ROOT, GetAncestor};
    use winit::raw_window_handle::{HasWindowHandle as _, RawWindowHandle};
    #[link(name = "dwmapi")]
    unsafe extern "system" {
        fn DwmSetWindowAttribute(hwnd: Handle, attribute: u32, value: *const i32, size: u32)
        -> i32;
    }
    let RawWindowHandle::Win32(root) = window
        .window_handle()
        .expect("Missing root window")
        .as_raw()
    else {
        panic!("The retained root needs a Win32 HWND");
    };
    let hwnd = root.hwnd.get();
    let handle = hwnd as Handle;
    let mut pid = 0;
    // SAFETY: the borrowed winit root is live and the owner PID output is writable.
    let tid = unsafe { GetWindowThreadProcessId(handle, &raw mut pid) };
    assert_eq!(pid, std::process::id());
    assert_eq!(tid, crate::win32_clock::thread_id());
    assert_eq!(HWND(handle), unsafe { GetAncestor(HWND(handle), GA_ROOT) });
    if mode == "ordinary" {
        println!("DWM_TRANSITIONS mode=ordinary hwnd={hwnd} pid={pid} tid={tid} set=0");
        return;
    }
    assert_eq!(mode, "disabled");
    // DWMWA_TRANSITIONS_FORCEDISABLED is a setter with a Win32 BOOL input. Its
    // scope ends with this HWND. The normal control leaves the attribute alone.
    const DWMWA_TRANSITIONS_FORCEDISABLED: u32 = 3;
    let disabled: i32 = 1;
    let hr = unsafe {
        DwmSetWindowAttribute(
            handle,
            DWMWA_TRANSITIONS_FORCEDISABLED,
            &raw const disabled,
            4,
        )
    };
    println!("DWM_TRANSITIONS mode=disabled hwnd={hwnd} pid={pid} tid={tid} set=1 hresult={hr}");
    assert_eq!(hr, 0, "DwmSetWindowAttribute did not return S_OK");
}
