//! Compare the linked binding with the system API in a native Windows ARM64 process.

#![cfg_attr(not(all(windows, target_arch = "aarch64")), allow(unused))]

#[cfg(not(all(windows, target_arch = "aarch64")))]
compile_error!("Run this observer in an ARM64 Windows process");

use std::ffi::{c_void, CStr};
use std::os::windows::ffi::OsStrExt;

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetCurrentProcess() -> *mut c_void;
    fn IsWow64Process2(process: *mut c_void, process_machine: *mut u16, native: *mut u16) -> i32;
    fn IsProcessorFeaturePresent(feature: u32) -> i32;
    fn LoadLibraryExW(path: *const u16, file: *mut c_void, flags: u32) -> *mut c_void;
    fn GetProcAddress(module: *mut c_void, name: *const u8) -> *mut c_void;
    fn FreeLibrary(module: *mut c_void) -> i32;
}

fn export(module: *mut c_void, name: &CStr) -> *mut c_void {
    // The module remains loaded for the lifetime of all retrieved function pointers.
    let pointer = unsafe { GetProcAddress(module, name.as_ptr().cast()) };
    assert!(!pointer.is_null(), "missing export {name:?}");
    pointer
}

fn main() {
    let mut process = 0xffff;
    let mut native = 0xffff;
    let checked = unsafe { IsWow64Process2(GetCurrentProcess(), &mut process, &mut native) };
    assert_ne!(checked, 0, "native architecture query failed");
    assert_eq!((process, native), (0, 0xaa64), "native ARM64 required");
    let path = std::path::PathBuf::from(std::env::args_os().nth(1).expect("absolute DLL path"));
    assert!(path.is_absolute());
    let wide: Vec<_> = path.as_os_str().encode_wide().chain([0]).collect();
    // The probe's only imported module is Kernel32. Restrict dependency lookup to System32.
    let module = unsafe { LoadLibraryExW(wide.as_ptr(), std::ptr::null_mut(), 0x800) };
    assert!(!module.is_null(), "{}", std::io::Error::last_os_error());
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
    assert_ne!(unsafe { FreeLibrary(module) }, 0);
    println!("{{\"nativeMachine\":43620,\"processMachine\":0,\"featureIdsMatched\":64,\"ringFeatureId\":30,\"ringFeaturePresent\":{}}}", crypto != 0);
}
