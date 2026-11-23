//! Project the contrast palette into this frame's root Ui and its existing controls.
use super::windows_appearance::{Palette, Rgb};
use eframe::egui::{Color32, Stroke, Ui, Widget};

fn color([r, g, b]: Rgb) -> Color32 {
    Color32::from_rgb(r, g, b)
}

pub(super) fn apply(ui: &mut Ui, palette: Option<Palette>) {
    let Some(p) = palette else { return };
    let text = if ui.is_enabled() {
        p.text
    } else {
        p.disabled_text
    };
    // A new root Ui inherits the current egui system theme each pass. The local
    // override ends with this frame, including when the ordinary theme has changed.
    let v = ui.visuals_mut();
    v.override_text_color = Some(color(text));
    v.window_fill = color(p.window);
    v.panel_fill = color(p.window);
    v.extreme_bg_color = color(p.window);
    v.text_edit_bg_color = Some(color(p.window));
    v.widgets.noninteractive.bg_fill = color(p.window);
    v.widgets.noninteractive.fg_stroke.color = color(text);
    v.window_stroke.color = color(text);
    v.widgets.noninteractive.bg_stroke.color = color(text);
    v.text_cursor.stroke.color = color(p.text);
    v.selection.bg_fill = color(p.highlight);
    v.selection.stroke = Stroke::new(2.0, color(p.highlight_text));
    v.hyperlink_color = color(p.link);
    v.weak_text_color = Some(color(p.disabled_text));
    // Egui normally fades disabled widgets. Windows supplies an actual text color.
    v.disabled_alpha = 1.0;
    for state in [
        &mut v.widgets.inactive,
        &mut v.widgets.hovered,
        &mut v.widgets.active,
        &mut v.widgets.open,
    ] {
        state.bg_fill = color(p.button);
        state.weak_bg_fill = color(p.button);
        state.bg_stroke = Stroke::new(1.0, color(p.button_text));
        state.fg_stroke.color = color(p.button_text);
    }
    v.widgets.hovered.bg_stroke = Stroke::new(2.0, color(p.button_text));
    v.widgets.active.bg_stroke = Stroke::new(2.0, color(p.button_text));
}

pub(super) enum TextRole {
    Window,
    Button,
}

// In egui 0.37 the default TextEdit and Button use the same inactive foreground.
// Inspect the Ui inside Widget::ui so add_enabled(false, ...) receives GRAYTEXT.
pub(super) fn control(
    palette: Option<Palette>,
    role: TextRole,
    widget: impl Widget,
) -> impl Widget {
    move |ui: &mut Ui| {
        let Some(p) = palette else {
            return widget.ui(ui);
        };
        let text = if !ui.is_enabled() {
            p.disabled_text
        } else {
            match role {
                TextRole::Window => p.text,
                TextRole::Button => p.button_text,
            }
        };
        let previous = ui.visuals().override_text_color;
        ui.visuals_mut().override_text_color = Some(color(text));
        let response = widget.ui(ui);
        ui.visuals_mut().override_text_color = previous;
        response
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use eframe::egui::{self, Button, Context, FontData, FontDefinitions, FontFamily, TextEdit};
    use std::collections::HashSet;
    use std::sync::Arc;

    const PALETTE: Palette = Palette {
        window: [23, 34, 45],
        text: [234, 215, 196],
        highlight: [55, 91, 148],
        highlight_text: [246, 249, 217],
        button: [48, 52, 62],
        button_text: [160, 242, 235],
        disabled_text: [144, 181, 179],
        link: [95, 202, 248],
    };

    #[test]
    fn system_theme_is_restored_after_changes_to_an_active_palette() {
        let ctx = Context::default();
        ctx.set_fonts(FontDefinitions::empty());
        let updated = Palette {
            window: [211, 205, 184],
            ..PALETTE
        };
        for (theme, palette) in [
            (egui::Theme::Light, None),
            (egui::Theme::Light, Some(PALETTE)),
            (egui::Theme::Light, Some(updated)),
            (egui::Theme::Dark, Some(updated)),
            (egui::Theme::Dark, None),
        ] {
            let original = ctx.style_of(theme).visuals.clone();
            ctx.run_ui(
                egui::RawInput {
                    system_theme: Some(theme),
                    ..Default::default()
                },
                |ui| {
                    apply(ui, palette);
                    if let Some(p) = palette {
                        assert_eq!(ui.visuals().panel_fill, color(p.window));
                        assert_eq!(ui.visuals().selection.bg_fill, color(p.highlight));
                        assert_eq!(ui.visuals().selection.stroke.color, color(p.highlight_text));
                        assert_eq!(ui.visuals().hyperlink_color, color(p.link));
                    } else {
                        assert_eq!(ui.visuals(), &original);
                    }
                },
            )
            .drop_without_applying_deltas();
            assert_eq!(ctx.style_of(theme).visuals, original);
        }
    }

    fn font_context() -> Context {
        let ctx = Context::default();
        let mut fonts = FontDefinitions::empty();
        fonts.font_data.insert(
            "qa".into(),
            Arc::new(FontData::from_static(include_bytes!(concat!(
                env!("IFW_QA_FONT_DIR"),
                "/NotoSans-Regular.ttf"
            )))),
        );
        for family in [FontFamily::Proportional, FontFamily::Monospace] {
            fonts.families.insert(family, vec!["qa".into()]);
        }
        ctx.set_fonts(fonts);
        ctx
    }

    fn mesh_colors(
        ctx: &Context,
        mut output: egui::FullOutput,
    ) -> (HashSet<Color32>, HashSet<Color32>) {
        output.textures_delta.clear();
        let mut glyphs = HashSet::new();
        let mut fills = HashSet::new();
        for primitive in ctx.tessellate(output.shapes, output.pixels_per_point) {
            if let egui::epaint::Primitive::Mesh(mesh) = primitive.primitive {
                for v in mesh.vertices {
                    if v.uv == egui::epaint::WHITE_UV {
                        fills.insert(v.color);
                    } else {
                        glyphs.insert(v.color);
                    }
                }
            }
        }
        (glyphs, fills)
    }

    #[test]
    fn rendered_control_text_uses_window_button_and_disabled_system_colors() {
        let ctx = font_context();
        for (button, enabled, expected) in [
            (false, true, PALETTE.text),
            (true, true, PALETTE.button_text),
            (false, false, PALETTE.disabled_text),
            (true, false, PALETTE.disabled_text),
        ] {
            let p = Some(PALETTE);
            let mut text = String::from("Sample");
            let output = ctx.run_ui(Default::default(), |ui| {
                apply(ui, p);
                egui::CentralPanel::default().show(ui, |ui| {
                    if button {
                        ui.add_enabled(
                            enabled,
                            control(p, TextRole::Button, Button::new("Sample")),
                        );
                    } else {
                        ui.add_enabled(
                            enabled,
                            control(p, TextRole::Window, TextEdit::singleline(&mut text)),
                        );
                    }
                });
            });
            let (glyphs, fills) = mesh_colors(&ctx, output);
            assert!(
                glyphs.contains(&color(expected)),
                "button={button} enabled={enabled}: {glyphs:?}"
            );
            assert!(fills.contains(&color(if button {
                PALETTE.button
            } else {
                PALETTE.window
            })));
        }
    }

    #[test]
    fn selected_editor_glyphs_and_selection_fill_use_the_two_highlight_colors() {
        use egui::text::{CCursor, CCursorRange};
        let ctx = font_context();
        let id = egui::Id::unique("selected");
        let mut text = String::from("Sample");
        let mut draw = |ui: &mut Ui| {
            let p = Some(PALETTE);
            apply(ui, p);
            ui.add(control(
                p,
                TextRole::Window,
                TextEdit::singleline(&mut text).id(id),
            ));
        };
        ctx.run_ui(Default::default(), &mut draw)
            .drop_without_applying_deltas();
        ctx.memory_mut(|m| m.request_focus(id));
        let mut state = TextEdit::load_state(&ctx, id).unwrap();
        state
            .cursor
            .set_char_range(Some(CCursorRange::two(CCursor::new(0), CCursor::new(6))));
        state.store(&ctx, id);
        let (glyphs, fills) = mesh_colors(&ctx, ctx.run_ui(Default::default(), draw));
        assert!(
            glyphs.contains(&color(PALETTE.highlight_text)),
            "{glyphs:?}"
        );
        assert!(fills.contains(&color(PALETTE.highlight)), "{fills:?}");
    }
}
