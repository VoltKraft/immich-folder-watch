//! Read the calling process's native performance counter and thread identity for the Windows QA trace.
#![cfg(windows)]

#[link(name = "kernel32")]
unsafe extern "system" {
    fn QueryPerformanceCounter(counter: *mut i64) -> i32;
    fn QueryPerformanceFrequency(frequency: *mut i64) -> i32;
    fn GetCurrentThreadId() -> u32;
}

pub fn counter() -> i64 {
    let mut value = 0;
    // LARGE_INTEGER has signed 64-bit size and alignment on both qualified Windows targets.
    // The writable stack value lives for the complete system call.
    assert!(unsafe { QueryPerformanceCounter(&mut value) } != 0);
    value
}

pub fn frequency() -> i64 {
    let mut value = 0;
    // The API initializes one LARGE_INTEGER, with the same lifetime as in counter().
    assert!(unsafe { QueryPerformanceFrequency(&mut value) } != 0);
    value
}

pub fn thread_id() -> u32 {
    // This query has no arguments, opens no handle and identifies only the calling thread.
    unsafe { GetCurrentThreadId() }
}
