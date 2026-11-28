//! A visible texture and two pipe-driven transitions in the private example only.
use eframe::egui::{self, Color32, ColorImage, TextureHandle, TextureId, TextureOptions};
use std::cell::RefCell;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicU8, Ordering};

static PHASE: AtomicU8 = AtomicU8::new(0);
static CONTEXT: OnceLock<egui::Context> = OnceLock::new();

pub(super) fn advance(next: u8) {
    PHASE
        .compare_exchange(next - 1, next, Ordering::SeqCst, Ordering::SeqCst)
        .expect("The observer must capture each texture phase in order");
    CONTEXT
        .get()
        .expect("The original scene is visible")
        .request_repaint();
}

struct Scene {
    original: TextureHandle,
    nearest: Option<TextureHandle>,
    applied: u8,
}

thread_local! {
    static SCENE: RefCell<Option<Scene>> = const { RefCell::new(None) };
}

fn managed(handle: &TextureHandle) -> u64 {
    match handle.id() {
        TextureId::Managed(id) => id,
        TextureId::User(_) => unreachable!("The egui texture manager owns the scene textures"),
    }
}

pub(super) fn paint(ui: &mut egui::Ui) {
    CONTEXT.get_or_init(|| ui.ctx().clone());
    SCENE.with_borrow_mut(|slot| {
        let state = slot.get_or_insert_with(|| {
            let original = ui.ctx().load_texture(
                "handoff-original",
                ColorImage::filled([8, 8], Color32::RED),
                TextureOptions::LINEAR,
            );
            println!("HANDOFF_FULL id={}", managed(&original));
            Scene {
                original,
                nearest: None,
                applied: 0,
            }
        });
        let phase = PHASE.load(Ordering::SeqCst);
        if phase == 1 && state.applied == 0 {
            state.original.set_partial(
                [2, 2],
                ColorImage::filled([4, 4], Color32::GREEN),
                TextureOptions::LINEAR,
            );
            println!("HANDOFF_PARTIAL id={}", managed(&state.original));
            state.applied = 1;
        } else if phase == 2 && state.applied == 1 {
            let nearest = ui.ctx().load_texture(
                "handoff-nearest",
                ColorImage::filled([2, 2], Color32::BLUE),
                TextureOptions::NEAREST,
            );
            println!("HANDOFF_NEAREST id={}", managed(&nearest));
            state.nearest = Some(nearest);
            state.applied = 2;
        }
        assert_eq!(phase, state.applied);
        let (area, _) = ui.allocate_exact_size(egui::vec2(176.0, 96.0), egui::Sense::hover());
        let base = egui::Rect::from_min_size(area.min, egui::vec2(96.0, 96.0));
        let mark =
            egui::Rect::from_min_size(area.min + egui::vec2(112.0, 16.0), egui::vec2(64.0, 64.0));
        let uv = egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0));
        ui.painter()
            .image(state.original.id(), base, uv, Color32::WHITE);
        if let Some(nearest) = &state.nearest {
            ui.painter().image(nearest.id(), mark, uv, Color32::WHITE);
        } else {
            ui.painter().rect_filled(mark, 0.0, Color32::BLACK);
        }
        let coords = [
            base.min + egui::vec2(9.0, 9.0),
            base.center(),
            mark.center(),
        ]
        .map(|p| (p.to_vec2() * ui.ctx().pixels_per_point()).round());
        println!(
            "HANDOFF_DRAW {phase} {} {} {} {} {} {} {}",
            managed(&state.original),
            coords[0].x,
            coords[0].y,
            coords[1].x,
            coords[1].y,
            coords[2].x,
            coords[2].y
        );
    });
}
