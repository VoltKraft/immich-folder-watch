//! One process exercises the dependencies selected by the combined development profile.
#![forbid(unsafe_code)]

#[path = "../../gui/src/fonts.rs"]
mod fonts;
mod legacy_upload;
mod upload_trial;

use desktop_lifecycle::{DesktopLifecycle, HostCommand};
use desktop_platform_log::{Level, Record};
use eframe::egui;
use ifw_immich::realtime::{EnginePacket, websocket_packet};
use ifw_legacy::timestamp::UtcTicks;
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{error::Error, io::Cursor, path::Path, sync::Arc};
use tokio_tungstenite::tungstenite::protocol::{Role, WebSocket};

#[derive(Debug, Deserialize, Eq, PartialEq, Serialize)]
struct Observation {
    file: String,
    utc: String,
}

fn draw(label: &str) -> usize {
    let context = egui::Context::default();
    let mut definitions = egui::FontDefinitions::empty();
    for (family, name, bytes) in [
        (
            egui::FontFamily::Proportional,
            "Noto Sans",
            include_bytes!("../../../../rust/assets/fonts/NotoSans-Regular.ttf").as_slice(),
        ),
        (
            egui::FontFamily::Monospace,
            "Noto Sans Mono",
            include_bytes!("../../../../rust/assets/fonts/NotoSansMono-Regular.ttf").as_slice(),
        ),
    ] {
        definitions
            .font_data
            .insert(name.into(), Arc::new(egui::FontData::from_static(bytes)));
        definitions
            .families
            .entry(family)
            .or_default()
            .push(name.into());
    }
    fonts::add_fallbacks(&mut definitions);
    context.set_fonts(definitions);
    let output = context.run_ui(egui::RawInput::default(), |ui| {
        ui.label(label);
    });
    assert!(!output.textures_delta.set.is_empty());
    context
        .tessellate(output.shapes, output.pixels_per_point)
        .len()
}

#[cfg(target_os = "linux")]
fn platform() -> Result<serde_json::Value, Box<dyn Error>> {
    use wayland_client::{Proxy, protocol::wl_surface::WlSurface};

    assert_eq!(WlSurface::interface().name, "wl_surface");
    let service = zbus::names::WellKnownName::try_from("org.freedesktop.portal.Desktop")?;
    assert_eq!(service.as_str(), "org.freedesktop.portal.Desktop");
    let blur = wayland_protocols_plasma::blur::client::org_kde_kwin_blur_manager::OrgKdeKwinBlurManager::interface();
    Ok(
        serde_json::json!({"binding": "wayland-interface-and-portal-name", "kdeBlurManagerVersion": blur.version}),
    )
}

#[cfg(windows)]
fn platform() -> Result<serde_json::Value, Box<dyn Error>> {
    use windows::Win32::UI::Shell::{NIF_TIP, NOTIFYICONDATAW};

    let icon = NOTIFYICONDATAW {
        uFlags: NIF_TIP,
        ..Default::default()
    };
    assert_eq!(icon.uFlags, NIF_TIP);
    Ok(serde_json::json!({"binding": "windows-shell-notifyicon-layout"}))
}

fn renderer_witness() -> Result<&'static str, Box<dyn Error>> {
    // A function item is zero-sized. Retain an actual native entry point.
    let entry: fn(&str, eframe::NativeOptions, eframe::AppCreator<'_>) -> eframe::Result =
        eframe::run_native;
    let entry = std::hint::black_box(entry);
    #[cfg(target_os = "linux")]
    {
        if std::env::var("IFW_QA_COMBINED_HEADLESS").as_deref() != Ok("private-namespace")
            || ["DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"]
                .iter()
                .any(|key| std::env::var_os(key).is_some())
        {
            return Err("renderer control requires the private display-free namespace".into());
        }
        let result = entry(
            "Combined profile headless control",
            eframe::NativeOptions::default(),
            Box::new(|_| Err("unexpected graphics window in the private control".into())),
        );
        match result {
            Err(eframe::Error::WinitEventLoop(error))
                if error
                    .to_string()
                    .contains("neither WAYLAND_DISPLAY nor WAYLAND_SOCKET nor DISPLAY is set") =>
            {
                Ok("winit-refused-missing-display")
            }
            other => Err(format!("unexpected headless renderer result: {other:?}").into()),
        }
    }
    #[cfg(windows)]
    {
        assert_ne!(entry as usize, 0);
        Ok("native-eframe-function-pointer")
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args_os().skip(1);
    let first = args.next().ok_or("missing synthetic root")?;
    if first == "--legacy-upload" {
        let root = args.next().ok_or("missing synthetic upload root")?;
        let display = args.next().ok_or("missing display path")?;
        if args.next().is_some() {
            return Err("unexpected legacy upload argument".into());
        }
        return upload_trial::observe(
            Path::new(&root),
            display.to_str().ok_or("invalid display text")?,
        );
    }
    // Only the runner-created fixture directory is passed to the filesystem adapter.
    let root = safe_fs::Directory::open_root(Path::new(&first))?;
    let media = root.open_file("sample.txt".as_ref())?;
    assert!(media.is_current_entry()?);

    let yaml = "file: sample.txt\nutc: '2026-11-21T00:00:00.0000001+00:00'\n";
    let row: Observation = serde_saphyr::from_str(yaml)?;
    assert_eq!(
        serde_saphyr::from_str::<Observation>(&serde_saphyr::to_string(&row)?)?,
        row
    );
    let utc = UtcTicks::parse_sql(&row.utc)?;
    #[cfg(target_os = "linux")]
    assert_eq!(UtcTicks::from_linux_mtime(&media.metadata()?)?, utc);
    let sql = Connection::open_in_memory()?;
    sql.execute(
        "CREATE TABLE sample (name TEXT, ticks TEXT, digest BLOB)",
        [],
    )?;
    sql.execute(
        "INSERT INTO sample VALUES (?1, ?2, ?3)",
        params![
            row.file,
            utc.format_sql(),
            &Sha256::digest(row.file.as_bytes())[..]
        ],
    )?;
    let name: String = sql.query_row(
        "SELECT name FROM sample WHERE ticks = ?1 AND length(digest) = 32",
        [&row.utc],
        |r| r.get(0),
    )?;
    assert_eq!(name, row.file);
    let sqlite_id: String = sql.query_row("SELECT sqlite_source_id()", [], |r| r.get(0))?;
    let extension: (i64, i64) = sql.query_row(
        "SELECT sqlite_compileoption_used('OMIT_LOAD_EXTENSION'), sqlite_compileoption_used('ENABLE_LOAD_EXTENSION')",
        [],
        |r| Ok((r.get(0)?, r.get(1)?)),
    )?;
    assert_eq!(extension, (1, 0));
    let mut lifecycle = DesktopLifecycle::new(true);
    assert_eq!(lifecycle.activate(), Some(HostCommand::ShowAndFocus));
    let mut log = Vec::new();
    Record {
        level: Level::Information,
        category: "fixture",
        event_id: 1,
        message: &name,
    }
    .write_file(&mut log, &row.utc)?;
    assert!(std::str::from_utf8(&log)?.contains(&name));

    let mut websocket =
        WebSocket::from_raw_socket(Cursor::new(b"\x81\x042abc".to_vec()), Role::Client, None);
    let text = websocket.read()?.into_text()?;
    assert_eq!(
        websocket_packet(text.as_bytes()),
        Ok(EnginePacket::Ping("abc"))
    );
    rustls::crypto::ring::default_provider()
        .install_default()
        .map_err(|_| "unexpected TLS provider")?;
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    let request = runtime.block_on(async {
        reqwest::Client::builder()
            .tls_backend_rustls()
            .tls_certs_only([])
            .https_only(true)
            .redirect(reqwest::redirect::Policy::none())
            .no_proxy()
            .build()?
            .get("https://example.invalid/fixture")
            .build()
    })?;
    assert_eq!(request.url().path(), "/fixture");
    let shapes = draw(&name);
    assert!(shapes > 0);
    println!(
        "{}",
        serde_json::json!({
            "marker": "combined-profile-v1", "nativeRenderer": renderer_witness()?, "roundTrip": row, "platform": platform()?,
            "sqliteSourceId": sqlite_id, "sqliteExtensionLoadingOmitted": extension.0 == 1, "tessellatedPrimitives": shapes, "websocketPing": "abc"
        })
    );
    Ok(())
}
