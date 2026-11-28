//! Portable control of the actual diagnostic recorder with a deterministic clock.
#![allow(non_snake_case)]
mod window_messages;
use std::sync::atomic::{AtomicI64, Ordering};

fn clock() -> i64 {
    static COUNTER: AtomicI64 = AtomicI64::new(10);
    COUNTER.fetch_add(1, Ordering::Relaxed)
}
unsafe fn GetCurrentThreadId() -> u32 {
    7
}

fn main() {
    use window_messages::{ROOT, default_proc, show, wndproc};
    assert!(wndproc(9, 24).is_none());
    assert!(show(9, 5).is_none());
    ROOT.set(9);
    assert!(show(10, 5).is_none());
    let first = show(9, 5).unwrap();
    let start = clock();
    assert!(wndproc(10, 24).is_none());
    std::thread::spawn(|| assert!(wndproc(9, 24).is_none()))
        .join()
        .unwrap();
    {
        let _message = wndproc(9, 24).unwrap();
        let _default = default_proc(9, 24).unwrap();
        let _nested = wndproc(9, 0xcccd).unwrap();
    }
    let end = clock();
    drop(first);
    assert!(default_proc(9, 24).is_none());
    let empty = show(9, 7).unwrap();
    let second_start = clock();
    let second_end = clock();
    drop(empty);
    println!("CALLS {start} {end} {second_start} {second_end}");
    window_messages::write(&mut std::io::stdout(), 1000).unwrap();
}
