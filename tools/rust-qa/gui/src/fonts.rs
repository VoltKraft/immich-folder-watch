//! Explicit fallback faces for both UI font families in the native assessment.
use eframe::egui::{FontData, FontDefinitions, FontFamily};
use std::sync::Arc;

pub(super) fn add_fallbacks(fonts: &mut FontDefinitions) {
    let faces: [(&str, &[u8]); 3] = [
        (
            "Noto Sans Symbols 2",
            include_bytes!(concat!(
                env!("IFW_QA_FALLBACK_DIR"),
                "/NotoSansSymbols2-Regular.ttf"
            )),
        ),
        (
            "Noto Sans Arabic",
            include_bytes!(concat!(
                env!("IFW_QA_FALLBACK_DIR"),
                "/NotoSansArabic-Regular.ttf"
            )),
        ),
        (
            "Noto Sans CJK JP",
            include_bytes!(concat!(
                env!("IFW_QA_FALLBACK_DIR"),
                "/NotoSansCJKjp-Regular.otf"
            )),
        ),
    ];
    for (name, bytes) in faces {
        fonts
            .font_data
            .insert(name.into(), Arc::new(FontData::from_static(bytes)));
        for family in [FontFamily::Proportional, FontFamily::Monospace] {
            fonts.families.entry(family).or_default().push(name.into());
        }
    }
}
