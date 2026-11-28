//! Reach winit's native thread check in two independent processes.
#![forbid(unsafe_code)]

use winit::event_loop::EventLoop;
use winit::platform::windows::EventLoopBuilderExtWindows;

fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("main-thread") => {
            // The event loop creates its internal message target without an application window.
            let event_loop = EventLoop::builder()
                .with_dpi_aware(false)
                .build()
                .expect("the primary thread must be able to create its event loop");
            drop(event_loop);
            println!("main-thread-created");
        }
        Some("worker-thread") => {
            let rejected = std::thread::spawn(|| {
                let _ = EventLoop::builder().with_dpi_aware(false).build();
            })
            .join()
            .expect_err("winit accepted the worker thread as its primary thread");
            let message = rejected
                .downcast_ref::<String>()
                .map(String::as_str)
                .or_else(|| rejected.downcast_ref::<&str>().copied())
                .unwrap_or_default();
            assert!(message.contains("Initializing the event loop outside of the main thread"));
            println!("worker-thread-rejected");
        }
        _ => panic!("specify main-thread or worker-thread"),
    }
}
