//! Development fixture. An isolated supervisor owns the model across native window lifetimes.
#![forbid(unsafe_code)]

#[cfg(target_os = "linux")]
mod linux;

use desktop_lifecycle::{DesktopLifecycle, HostCommand, Shutdown, WindowIntent};
use eframe::egui;
use std::cell::RefCell;
use std::error::Error;
use std::rc::Rc;
use std::sync::mpsc::{self, Receiver, SyncSender, TrySendError};
use std::sync::{Arc, Mutex};

#[derive(Clone, Copy, Debug)]
enum Command {
    Open,
    Close,
    Quit,
}

#[derive(Clone)]
struct Control {
    sender: SyncSender<Command>,
    window: Arc<Mutex<Option<egui::Context>>>,
}

impl Control {
    fn send(&self, command: Command) -> Result<(), TrySendError<Command>> {
        self.sender.try_send(command)?;
        if let Some(ctx) = &*self.window.lock().expect("window wake mutex poisoned") {
            ctx.request_repaint();
        }
        Ok(())
    }
}

struct Model {
    lifecycle: DesktopLifecycle,
    commands: Receiver<Command>,
    filename: String,
    password: String,
    german: bool,
    passes: u64,
}

impl Model {
    fn command(&mut self, command: Command) -> Option<HostCommand> {
        match command {
            Command::Open => self.lifecycle.activate(),
            Command::Close => self.lifecycle.close_window(),
            Command::Quit => self.lifecycle.request_quit(),
        }
    }
}

struct Window {
    model: Rc<RefCell<Model>>,
    control: Control,
}

impl Window {
    fn new(
        creation: &eframe::CreationContext<'_>,
        model: Rc<RefCell<Model>>,
        control: Control,
    ) -> Self {
        let mut fonts = egui::FontDefinitions::empty();
        for (family, name, data) in [
            (
                egui::FontFamily::Proportional,
                "Noto Sans",
                include_bytes!(concat!(env!("IFW_QA_FONT_DIR"), "/NotoSans-Regular.ttf"))
                    .as_slice(),
            ),
            (
                egui::FontFamily::Monospace,
                "Noto Sans Mono",
                include_bytes!(concat!(
                    env!("IFW_QA_FONT_DIR"),
                    "/NotoSansMono-Regular.ttf"
                ))
                .as_slice(),
            ),
        ] {
            fonts
                .font_data
                .insert(name.to_owned(), Arc::new(egui::FontData::from_static(data)));
            fonts
                .families
                .entry(family)
                .or_default()
                .push(name.to_owned());
        }
        creation.egui_ctx.set_fonts(fonts);
        if let Some(render) = &creation.wgpu_render_state {
            let info = render.adapter.get_info();
            println!(
                "ADAPTER {:?} {:?} {}",
                info.backend, info.device_type, info.name
            );
        }
        *control.window.lock().expect("window wake mutex poisoned") =
            Some(creation.egui_ctx.clone());
        // The first frame drains any commands queued before the context was attached.
        creation.egui_ctx.request_repaint();
        Self { model, control }
    }
}

impl Drop for Window {
    fn drop(&mut self) {
        *self
            .control
            .window
            .lock()
            .expect("window wake mutex poisoned") = None;
    }
}

impl eframe::App for Window {
    fn logic(&mut self, ctx: &egui::Context, _: &mut eframe::Frame) {
        let mut model = self.model.borrow_mut();
        // Count native composition stages without disclosing entered text.
        ctx.input(|i| {
            for event in &i.events {
                match event {
                    egui::Event::Ime(egui::ImeEvent::Preedit { text, .. }) => {
                        println!("IME preedit chars={}", text.chars().count())
                    }
                    egui::Event::Ime(egui::ImeEvent::Commit(text)) => {
                        println!("IME commit chars={}", text.chars().count())
                    }
                    _ => (),
                }
            }
        });
        if ctx.input(|i| i.viewport().close_requested()) {
            if model.lifecycle.shutdown() == Shutdown::Running {
                model.lifecycle.close_window();
            }
            // Allow this native window session to end. The supervisor continues to receive activation.
            return;
        }
        while let Ok(command) = model.commands.try_recv() {
            match model.command(command) {
                Some(HostCommand::ShowAndFocus) => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Focus)
                }
                Some(HostCommand::Hide | HostCommand::StopBackground) => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                    break;
                }
                _ => (),
            }
        }
    }

    fn ui(&mut self, ui: &mut egui::Ui, _: &mut eframe::Frame) {
        let mut model = self.model.borrow_mut();
        model.passes += 1;
        ui.ctx()
            .accesskit_node_builder(egui::accesskit_root_id(), |root| {
                root.set_label("Desktop input probe")
            });
        egui::CentralPanel::default().show(ui, |ui| {
            let de = model.german;
            let label = ui.label(if de { "Dateiname" } else { "Filename" });
            ui.text_edit_singleline(&mut model.filename)
                .labelled_by(label.id);
            let label = ui.label(if de { "Kennwort" } else { "Password" });
            if ui
                .add(egui::TextEdit::singleline(&mut model.password).password(true))
                .labelled_by(label.id)
                .changed()
            {
                println!("EDIT masked chars={}", model.password.chars().count());
            }
            if ui.button(if de { "English" } else { "Deutsch" }).clicked() {
                model.german = !de;
            }
        });
    }
}

fn supervise(model: Rc<RefCell<Model>>, control: &Control) -> Result<(), Box<dyn Error>> {
    loop {
        let intent = model.borrow().lifecycle.window_intent();
        if model.borrow().lifecycle.shutdown() != Shutdown::Running {
            break;
        }
        if intent == WindowIntent::Visible {
            let options = eframe::NativeOptions {
                viewport: egui::ViewportBuilder::default()
                    .with_title("Desktop input probe")
                    .with_app_id("org.example.IfwGuiProbe")
                    .with_inner_size([640.0, 400.0]),
                renderer: eframe::Renderer::Wgpu,
                persist_window: false,
                run_and_return: true,
                ..Default::default()
            };
            let current = Rc::clone(&model);
            let control = control.clone();
            eframe::run_native(
                "Desktop input probe",
                options,
                Box::new(move |ctx| Ok(Box::new(Window::new(ctx, current, control)))),
            )?;
            let mut model = model.borrow_mut();
            // Some compositors end the window session without a prior CloseRequested event.
            if model.lifecycle.window_intent() == WindowIntent::Visible {
                model.lifecycle.close_window();
            }
            println!("WINDOW_RELEASED passes={}", model.passes);
        } else {
            let mut model = model.borrow_mut();
            let command = model.commands.recv()?;
            model.command(command);
        }
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    if std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1") {
        return Err("Use the synthetic isolated native QA launcher".into());
    }
    let background = match std::env::args().nth(1).as_deref() {
        Some("--background") => true,
        None => false,
        _ => return Err("Expected no argument or --background".into()),
    };
    let (sender, commands) = mpsc::sync_channel(8);
    let control = Control {
        sender,
        window: Arc::new(Mutex::new(None)),
    };
    #[cfg(target_os = "linux")]
    let (native, available) = linux::start(control.clone())?;
    #[cfg(target_os = "windows")]
    let (native, available) = windows_fixture_input(control.clone())?;
    let mut lifecycle = DesktopLifecycle::new(background);
    lifecycle.tray_result(available);
    println!(
        "READY {:?} {:?}",
        lifecycle.window_intent(),
        lifecycle.tray()
    );
    let model = Rc::new(RefCell::new(Model {
        lifecycle,
        commands,
        filename: "Grüße – Sommer.jpg".to_owned(),
        password: String::new(),
        german: true,
        passes: 0,
    }));
    let result = supervise(Rc::clone(&model), &control);
    #[cfg(target_os = "linux")]
    futures_lite::future::block_on(native.graceful_shutdown());
    #[cfg(target_os = "windows")]
    if result.is_ok() {
        native.join().map_err(|_| "QA control worker failed")?;
    }
    result?;
    if model.borrow_mut().lifecycle.background_stopped() != Some(HostCommand::ExitEventLoop) {
        return Err("Unexpected supervisor shutdown state".into());
    }
    println!("DRAINED passes={}", model.borrow().passes);
    Ok(())
}

// A native Windows runner can supply a measured tray result and controls on its private inherited pipe.
// This fixture alone provides no Shell_NotifyIcon or installed Windows evidence.
#[cfg(target_os = "windows")]
fn windows_fixture_input(
    control: Control,
) -> Result<(std::thread::JoinHandle<()>, bool), Box<dyn Error>> {
    use std::io::Read;
    let mut input = std::io::stdin();
    let mut next = [0];
    input.read_exact(&mut next)?;
    let available = match next[0] {
        b'T' => true,
        b'N' => false,
        _ => return Err("Expected an initial tray result".into()),
    };
    let handle = std::thread::spawn(move || {
        loop {
            let command = match input.read_exact(&mut next) {
                Ok(()) if next[0] == b'O' => Command::Open,
                Ok(()) if next[0] == b'C' => Command::Close,
                _ => Command::Quit,
            };
            if control.send(command).is_err() || matches!(command, Command::Quit) {
                break;
            }
        }
    });
    Ok((handle, available))
}
