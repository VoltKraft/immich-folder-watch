//! Project the platform preference into egui on the window's owning thread.
use super::linux_appearance::{Appearance, Scheme};
use eframe::egui::{Color32, Context, Stroke, Theme, ThemePreference, Visuals};

pub(super) fn apply(context: &Context, state: Appearance) {
    context.set_theme(match state.scheme {
        Scheme::System => ThemePreference::System,
        Scheme::Dark => ThemePreference::Dark,
        Scheme::Light => ThemePreference::Light,
    });
    let theme = context.theme();
    let (mut visuals, ink, paper) = match theme {
        Theme::Dark => (Visuals::dark(), Color32::WHITE, Color32::BLACK),
        Theme::Light => (Visuals::light(), Color32::BLACK, Color32::WHITE),
    };
    if state.high_contrast {
        visuals.override_text_color = Some(ink);
        visuals.window_fill = paper;
        visuals.panel_fill = paper;
        visuals.extreme_bg_color = paper;
        visuals.text_edit_bg_color = Some(paper);
        visuals.selection.bg_fill = match theme {
            Theme::Dark => Color32::from_rgb(0, 45, 110),
            Theme::Light => Color32::from_rgb(165, 215, 255),
        };
        visuals.selection.stroke = Stroke::new(2.0, ink);
        for widget in [
            &mut visuals.widgets.inactive,
            &mut visuals.widgets.hovered,
            &mut visuals.widgets.active,
            &mut visuals.widgets.open,
        ] {
            widget.bg_fill = paper;
            widget.weak_bg_fill = paper;
            widget.bg_stroke = Stroke::new(1.0, ink);
            widget.fg_stroke = Stroke::new(2.0, ink);
        }
        visuals.widgets.active.bg_stroke.width = 3.0;
    }
    context.set_visuals_of(theme, visuals);
}
