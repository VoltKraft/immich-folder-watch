//! Report one controlled driver error after the private software queue completes its real work.
use super::{Ordering, c_char, c_void, store};
use std::ffi::CStr;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicBool, AtomicPtr};

#[cfg(not(all(target_os = "linux", target_pointer_width = "64")))]
compile_error!("This Vulkan QA ABI is restricted to native 64-bit Linux");

type Submit = unsafe extern "system" fn(*mut c_void, u32, *const c_void, *mut c_void) -> i32;
type WaitIdle = unsafe extern "system" fn(*mut c_void) -> i32;
static SUBMIT: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static WAIT_IDLE: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());
static USED: AtomicBool = AtomicBool::new(false);
static ISOLATED: OnceLock<bool> = OnceLock::new();

pub(super) unsafe fn resolve(name: *const c_char, actual: *mut c_void) -> Option<*mut c_void> {
    if actual.is_null() {
        return None;
    }
    match unsafe { CStr::from_ptr(name) } {
        name if name == c"vkQueueSubmit" => {
            store(&SUBMIT, actual);
            Some(submit as *mut c_void)
        }
        name if name == c"vkQueueWaitIdle" => {
            store(&WAIT_IDLE, actual);
            None
        }
        _ => None,
    }
}

unsafe extern "system" fn submit(
    queue: *mut c_void,
    count: u32,
    infos: *const c_void,
    fence: *mut c_void,
) -> i32 {
    let forward: Submit = unsafe { std::mem::transmute(SUBMIT.load(Ordering::SeqCst)) };
    let result = unsafe { forward(queue, count, infos, fence) };
    if result == 0
        && *ISOLATED.get_or_init(|| {
            std::env::var("IFW_QA_GRAPHICS").as_deref() == Ok("driver-loss")
                && std::env::var("IFW_QA_ISOLATED").as_deref() == Ok("1")
                && std::env::var("DBUS_SESSION_BUS_ADDRESS").as_deref()
                    == Ok("unix:path=/tmp/session-bus")
                && std::env::var("VK_DRIVER_FILES").is_ok_and(|v| {
                    v.starts_with("/usr/share/vulkan/icd.d/lvp_icd.") && !v.contains(':')
                })
                && !std::path::Path::new("/dev/dri").exists()
        })
        && !USED.load(Ordering::Acquire)
        && std::fs::remove_file("/qa/fault-on-next-submit").is_ok()
    {
        // Vulkan retains access to submitted buffers until completion. The private ICD stays
        // healthy after the injected status, so let its real queue finish before wgpu releases
        // resources for a lost device. This is the same queue and externally synchronized call.
        USED.store(true, Ordering::Release);
        let address = WAIT_IDLE.load(Ordering::SeqCst);
        if address.is_null() {
            eprintln!("GRAPHICS_DRIVER_ERROR vkQueueWaitIdle was not resolved");
            return result;
        }
        let wait: WaitIdle = unsafe { std::mem::transmute(address) };
        let start = std::time::Instant::now();
        let idle = unsafe { wait(queue) };
        println!(
            "GRAPHICS_DRIVER_QUEUE_IDLE result={idle} elapsed_us={}",
            start.elapsed().as_micros()
        );
        if idle != 0 {
            // The independent observer requires VK_SUCCESS from both real driver calls.
            return idle;
        }
        println!(
            "GRAPHICS_DRIVER_SIGNAL vkQueueSubmit returned VK_ERROR_DEVICE_LOST after VK_SUCCESS"
        );
        -4 // VK_ERROR_DEVICE_LOST
    } else {
        result
    }
}
