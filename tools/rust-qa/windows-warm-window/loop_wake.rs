//! Wake winit's dispatcher even when Windows suppresses paint on the root HWND.
use eframe::{UserEvent, egui};
use std::sync::OnceLock;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;
use winit::event_loop::{EventLoop, EventLoopProxy};

#[derive(Default)]
pub(super) struct LoopWake {
    proxy: OnceLock<EventLoopProxy<UserEvent>>,
    last_pass: AtomicU64,
}

impl LoopWake {
    pub(super) fn install(&self, event_loop: &EventLoop<UserEvent>) {
        self.proxy.get_or_init(|| event_loop.create_proxy());
    }

    pub(super) fn observe(&self, ctx: &egui::Context) {
        self.last_pass.store(
            ctx.cumulative_pass_nr_for(egui::ViewportId::ROOT),
            Ordering::Relaxed,
        );
    }

    pub(super) fn notify(&self) {
        if let Some(proxy) = self.proxy.get() {
            // The application drains its command channel in user_event, before eframe
            // decides whether this viewport still needs the requested repaint.
            let _ = proxy.send_event(UserEvent::RequestRepaint {
                viewport_id: egui::ViewportId::ROOT,
                when: Instant::now(),
                cumulative_pass_nr: self.last_pass.load(Ordering::Relaxed),
            });
        }
    }
}
