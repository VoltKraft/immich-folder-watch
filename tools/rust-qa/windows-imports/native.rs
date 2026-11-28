//! Compare linked bindings with the independent system APIs in a native Windows process.

#[cfg(not(all(windows, any(target_arch = "aarch64", target_arch = "x86_64"))))]
compile_error!("Run this observer in a native Windows ARM64 or x64 process");

use std::ffi::{c_void, CStr};
use std::os::windows::ffi::OsStrExt;

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetCurrentProcess() -> *mut c_void;
    fn IsWow64Process2(process: *mut c_void, process_machine: *mut u16, native: *mut u16) -> i32;
    #[cfg(target_arch = "aarch64")]
    fn IsProcessorFeaturePresent(feature: u32) -> i32;
    #[cfg(target_arch = "x86_64")]
    fn GetCurrentThreadId() -> u32;
    fn LoadLibraryExW(path: *const u16, file: *mut c_void, flags: u32) -> *mut c_void;
    fn GetProcAddress(module: *mut c_void, name: *const u8) -> *mut c_void;
    fn FreeLibrary(module: *mut c_void) -> i32;
}

#[cfg(target_arch = "x86_64")]
#[link(name = "user32")]
unsafe extern "system" {
    fn GetSystemMetrics(index: i32) -> i32;
}

fn export(module: *mut c_void, name: &CStr) -> *mut c_void {
    // The module remains loaded for the lifetime of all retrieved function pointers.
    let pointer = unsafe { GetProcAddress(module, name.as_ptr().cast()) };
    assert!(!pointer.is_null(), "missing export {name:?}");
    pointer
}

#[cfg(target_arch = "aarch64")]
fn observe(module: *mut c_void) {
    // These signatures match the two no_mangle Rust exports in probe.rs.
    let feature: extern "system" fn(u32) -> i32 =
        unsafe { std::mem::transmute(export(module, c"ifw_feature")) };
    let ring: extern "system" fn() -> i32 =
        unsafe { std::mem::transmute(export(module, c"ifw_ring_feature")) };
    for id in 0..64 {
        assert_eq!(feature(id), unsafe { IsProcessorFeaturePresent(id) });
    }
    let crypto = unsafe { IsProcessorFeaturePresent(30) };
    assert_eq!(ring(), crypto);
    println!("{{\"nativeMachine\":43620,\"processMachine\":0,\"featureIdsMatched\":64,\"ringFeatureId\":30,\"ringFeaturePresent\":{}}}", crypto != 0);
}

#[cfg(target_arch = "x86_64")]
fn observe(module: *mut c_void) {
    // Both function types match the exports in probe_x64.rs. The worker joins before unloading.
    let thread_id: extern "system" fn() -> u32 =
        unsafe { std::mem::transmute(export(module, c"ifw_current_thread_id")) };
    let metric: extern "system" fn(i32) -> i32 =
        unsafe { std::mem::transmute(export(module, c"ifw_system_metric")) };
    let current = thread_id();
    assert_ne!(current, 0);
    assert_eq!(current, unsafe { GetCurrentThreadId() });
    let worker = std::thread::spawn(move || {
        let id = thread_id();
        assert_ne!(id, 0);
        assert_eq!(id, unsafe { GetCurrentThreadId() });
        id
    })
    .join()
    .expect("worker thread query");
    assert_ne!(current, worker);
    // Winit uses these virtual desktop metrics for its Windows desktop bounds.
    for index in 76..=79 {
        assert_eq!(metric(index), unsafe { GetSystemMetrics(index) });
    }
    println!("{{\"nativeMachine\":34404,\"processMachine\":0,\"distinctLiveThreads\":2,\"desktopMetricsMatched\":4}}");
}

fn main() {
    let mut process = 0xffff;
    let mut native = 0xffff;
    let checked = unsafe { IsWow64Process2(GetCurrentProcess(), &mut process, &mut native) };
    assert_ne!(checked, 0, "native architecture query failed");
    #[cfg(target_arch = "aarch64")]
    let expected = 0xaa64;
    #[cfg(target_arch = "x86_64")]
    let expected = 0x8664;
    assert_eq!((process, native), (0, expected), "native target required");
    let path = std::path::PathBuf::from(std::env::args_os().nth(1).expect("absolute DLL path"));
    assert!(path.is_absolute());
    let wide: Vec<_> = path.as_os_str().encode_wide().chain([0]).collect();
    // All probe dependencies are Windows system DLLs. Restrict lookup to System32.
    let module = unsafe { LoadLibraryExW(wide.as_ptr(), std::ptr::null_mut(), 0x800) };
    assert!(!module.is_null(), "{}", std::io::Error::last_os_error());
    observe(module);
    assert_ne!(unsafe { FreeLibrary(module) }, 0);
}
