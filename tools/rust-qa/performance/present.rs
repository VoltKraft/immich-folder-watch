//! Linux QA observer for the pinned ash dynamic-loader path and the one selected Mesa ICD.
//! The ordinary resource runs use the system loader directly.
use std::ffi::{CStr, c_char, c_int, c_void};
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::sync::atomic::{AtomicPtr, Ordering};
use std::sync::{Mutex, OnceLock};

type Resolve = unsafe extern "system" fn(*mut c_void, *const c_char) -> *mut c_void;
type Present = unsafe extern "system" fn(*mut c_void, *const c_void) -> i32;
static INSTANCE: OnceLock<Resolve> = OnceLock::new();
static DEVICE: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static PRESENT: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static COUNTER: OnceLock<Mutex<File>> = OnceLock::new();

#[link(name = "dl")]
unsafe extern "C" {
    fn dlopen(file: *const c_char, flags: c_int) -> *mut c_void;
    fn dlsym(handle: *mut c_void, symbol: *const c_char) -> *mut c_void;
}

fn emit(value: u8) {
    let stream = COUNTER.get_or_init(|| {
        let raw: u32 = std::env::var("IFW_QA_RENDER_FD").unwrap().parse().unwrap();
        Mutex::new(
            OpenOptions::new()
                .write(true)
                .open(format!("/proc/self/fd/{raw}"))
                .unwrap(),
        )
    });
    stream.lock().unwrap().write_all(&[value]).unwrap();
}

fn store(slot: &AtomicPtr<c_void>, value: *mut c_void) -> bool {
    match slot.compare_exchange(
        std::ptr::null_mut(),
        value,
        Ordering::SeqCst,
        Ordering::SeqCst,
    ) {
        Ok(_) => true,
        Err(previous) if previous == value => false,
        // This private single-ICD observer cannot mix per-device dispatch tables.
        Err(_) => std::process::abort(),
    }
}

// Vulkan supplies a valid NUL-terminated command name and handles. The observer forwards
// all unchanged arguments, intercepting only the exact two signatures declared above.
#[unsafe(no_mangle)]
unsafe extern "system" fn vkGetInstanceProcAddr(
    instance: *mut c_void,
    name: *const c_char,
) -> *mut c_void {
    let resolve = INSTANCE.get_or_init(|| {
        // The launcher binds the host's resolved system library at this private, immutable name.
        let handle = unsafe { dlopen(c"/qa-vulkan-system.so.1".as_ptr(), 2) };
        assert!(!handle.is_null());
        let address = unsafe { dlsym(handle, c"vkGetInstanceProcAddr".as_ptr()) };
        assert!(!address.is_null());
        unsafe { std::mem::transmute::<*mut c_void, Resolve>(address) }
    });
    let actual = unsafe { resolve(instance, name) };
    if !actual.is_null() && unsafe { CStr::from_ptr(name) } == c"vkGetDeviceProcAddr" {
        store(&DEVICE, actual);
        get_device as *mut c_void
    } else {
        actual
    }
}

unsafe extern "system" fn get_device(device: *mut c_void, name: *const c_char) -> *mut c_void {
    let address = DEVICE.load(Ordering::SeqCst);
    let resolve: Resolve = unsafe { std::mem::transmute(address) };
    let actual = unsafe { resolve(device, name) };
    if !actual.is_null() && unsafe { CStr::from_ptr(name) } == c"vkQueuePresentKHR" {
        if store(&PRESENT, actual) {
            emit(b'R');
        }
        present as *mut c_void
    } else {
        actual
    }
}

unsafe extern "system" fn present(queue: *mut c_void, info: *const c_void) -> i32 {
    let address = PRESENT.load(Ordering::SeqCst);
    let forward: Present = unsafe { std::mem::transmute(address) };
    let result = unsafe { forward(queue, info) };
    if matches!(result, 0 | 1_000_001_003) {
        // VK_SUCCESS / VK_SUBOPTIMAL_KHR
        emit(b'F');
    }
    result
}
