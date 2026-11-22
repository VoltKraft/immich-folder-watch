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
    single: OnceLock<bool>,
}

impl LoopWake {
    pub(super) fn install(&self, event_loop: &EventLoop<UserEvent>) {
        self.proxy.get_or_init(|| event_loop.create_proxy());
    }

    pub(super) fn single(&self) -> bool {
        *self.single.get_or_init(|| {
            std::env::var("IFW_QA_ISOLATED").as_deref() == Ok("1")
                && std::env::var("IFW_QA_WINDOWS_SINGLE_WAKE").as_deref() == Ok("1")
        })
    }

    fn private_viewport() -> egui::ViewportId {
        egui::ViewportId::from_hash_of("ifw-qa-private-control-wake")
    }

    pub(super) fn consumes(&self, event: &UserEvent) -> bool {
        self.single()
            && matches!(event, UserEvent::RequestRepaint { viewport_id, .. } if *viewport_id == Self::private_viewport())
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
                viewport_id: if self.single() {
                    Self::private_viewport()
                } else {
                    egui::ViewportId::ROOT
                },
                when: Instant::now(),
                cumulative_pass_nr: self.last_pass.load(Ordering::Relaxed),
            });
        }
    }
}
