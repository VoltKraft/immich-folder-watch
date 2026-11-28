//! Development-only observations from the actual TextEdit galley and rendered viewport.
use eframe::egui;
use std::fmt::Write as _;
use std::io::{BufWriter, Write as _};
use std::sync::Arc;

pub(super) fn filename() -> String {
    match std::env::var("IFW_FONT_CASE").as_deref() {
        Ok("glyphs") => "あ界⬟.jpg",
        Ok("mixed") => "L-بتث-R.jpg",
        Ok("numbers") => "L-ب12ت-R.jpg",
        _ => panic!("Select a synthetic font case"),
    }
    .to_owned()
}

pub(super) fn register(fonts: &mut egui::FontDefinitions) {
    match std::env::var("IFW_FONT_PROFILE").as_deref() {
        Ok("latin") => return,
        Ok("fallback") => (),
        _ => panic!("Select one of the two assessed font profiles"),
    }
    for (name, bytes) in [
        (
            "Noto Sans Symbols 2",
            &include_bytes!("../fonts/NotoSansSymbols2-Regular.ttf")[..],
        ),
        (
            "Noto Sans Arabic",
            &include_bytes!("../fonts/NotoSansArabic-Regular.ttf")[..],
        ),
        (
            "Noto Sans CJK JP",
            &include_bytes!("../fonts/NotoSansCJKjp-Regular.otf")[..],
        ),
    ] {
        fonts
            .font_data
            .insert(name.into(), Arc::new(egui::FontData::from_static(bytes)));
        for family in [egui::FontFamily::Proportional, egui::FontFamily::Monospace] {
            fonts.families.entry(family).or_default().push(name.into());
        }
    }
}

pub(super) fn filename_edit(ui: &mut egui::Ui, text: &mut String, label: egui::Id) {
    let edit_font = egui::FontId::proportional(30.0);
    let output = egui::TextEdit::singleline(text)
        .font(edit_font.clone())
        .desired_width(574.0)
        .show(ui);
    output.response.response.clone().labelled_by(label);
    let scale = ui.ctx().pixels_per_point();
    let field_focused = ui.memory(|memory| memory.has_focus(output.response.id));
    let clicked = output.response.clicked();
    let field = output.response.rect;
    let pass = ui.ctx().cumulative_pass_nr();
    // Observe what reached egui after the window system processed the fixture's
    // pointer commands. Do not request focus or change the field's interaction.
    ui.input(|input| {
        let (x, y) = input.pointer.hover_pos().map_or((-1, -1), |p| {
            ((p.x * scale).round() as i32, (p.y * scale).round() as i32)
        });
        println!(
            "FONT_POINTER {pass} {x} {y} {} {} {}",
            input.focused,
            output.response.contains_pointer(),
            input.pointer.primary_down()
        );
        for event in &input.raw.events {
            let (kind, pos) = match event {
                egui::Event::PointerMoved(pos) => ("move", Some(pos)),
                egui::Event::PointerButton {
                    pos,
                    button: egui::PointerButton::Primary,
                    pressed,
                    ..
                } => (if *pressed { "down" } else { "up" }, Some(pos)),
                egui::Event::PointerGone => ("gone", None),
                egui::Event::WindowFocused(true) => ("focus-in", None),
                egui::Event::WindowFocused(false) => ("focus-out", None),
                _ => continue,
            };
            let (x, y, inside) = pos.map_or((-1, -1, false), |p| {
                (
                    (p.x * scale).round() as i32,
                    (p.y * scale).round() as i32,
                    field.contains(*p),
                )
            });
            println!(
                "FONT_INPUT {pass} {kind} {x} {y} {inside} {} {field_focused} {clicked}",
                input.focused
            );
        }
    });
    let cursor = output.cursor_range.map(|r| {
        let caret = output.galley.pos_from_cursor(r.primary);
        let x = (output.galley_pos.x + caret.center().x) * scale;
        (r.primary.index, r.secondary.index, x.round() as i32)
    });
    let state = (cursor, text.clone());
    let changed = ui.data_mut(|d| {
        let key = egui::Id::unique("font-observer-last-value");
        if d.get_temp(key).as_ref() == Some(&state) {
            false
        } else {
            d.insert_temp(key, state);
            true
        }
    });
    if changed {
        let (a, b, x) = cursor.map_or((-1, -1, -1), |(a, b, x)| (a.0 as i32, b.0 as i32, x));
        let mut glyphs = String::new();
        for row in &output.galley.rows {
            for g in &row.glyphs {
                let x = (output.galley_pos.x + row.pos.x + g.pos.x) * scale;
                write!(
                    glyphs,
                    " {:X}:{:.2}:{:.2}",
                    g.chr as u32,
                    x,
                    g.advance_width * scale
                )
                .unwrap();
            }
        }
        println!(
            "FONT_FIELD\t{a}\t{b}\t{:.2}\t{x}\t{text}\t{glyphs}",
            output.response.rect.center().y * scale
        );
    }

    let key = egui::Id::unique("font-frame-requested");
    let capture = ui.data_mut(|d| d.get_temp::<bool>(key) != Some(true));
    ui.horizontal(|ui| {
        for ch in ['A', 'あ', '界', '⬟', 'ب', 'ت', 'ث', '\u{10fffd}'] {
            let (rect, _) = ui.allocate_exact_size(egui::vec2(52.0, 64.0), egui::Sense::hover());
            ui.painter().rect_filled(rect, 0.0, egui::Color32::BLACK);
            ui.painter().text(
                rect.center(),
                egui::Align2::CENTER_CENTER,
                ch,
                edit_font.clone(),
                egui::Color32::WHITE,
            );
            if capture {
                let has = ui.ctx().fonts_mut(|f| f.has_glyph(&edit_font, ch));
                println!(
                    "FONT_CELL {:X} {has} {:.0} {:.0} {:.0} {:.0}",
                    ch as u32,
                    rect.min.x * scale,
                    rect.min.y * scale,
                    rect.max.x * scale,
                    rect.max.y * scale
                );
            }
        }
    });
    if capture {
        ui.data_mut(|d| d.insert_temp(key, true));
        ui.ctx().request_screenshot(|image| {
            let destination =
                std::fs::File::create_new("observed.ppm").expect("fresh synthetic output");
            let mut output = BufWriter::new(destination);
            write!(output, "P6\n{} {}\n255\n", image.size[0], image.size[1]).unwrap();
            for pixel in &image.pixels {
                output.write_all(&pixel.to_array()[..3]).unwrap();
            }
            output.flush().unwrap();
            println!("FONT_FRAME {} {}", image.size[0], image.size[1]);
        });
    }
}
