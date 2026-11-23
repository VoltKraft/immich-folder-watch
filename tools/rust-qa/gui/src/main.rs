//! Development fixture. An isolated supervisor owns the model across native window lifetimes.
#![forbid(unsafe_code)]

#[cfg(windows)]
use native_gui_assessment::windows_appearance;
#[cfg(all(test, not(windows)))]
mod windows_appearance;
#[cfg(any(windows, test))]
mod windows_style;

#[cfg(target_os = "linux")]
mod appearance_style;
#[cfg(target_os = "linux")]
mod benchmark;
#[cfg(target_os = "windows")]
#[path = "windows_worker.rs"]
mod benchmark;
mod fonts;
#[cfg(windows)]
mod foreground_request;
mod graphics;
#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "linux")]
mod linux_appearance;
mod native_window;

use desktop_lifecycle::{DesktopLifecycle, HostCommand, Shutdown, WindowIntent};
use eframe::egui;
use std::cell::RefCell;
use std::error::Error;
use std::rc::Rc;
use std::sync::mpsc::{self, Receiver, SyncSender, TrySendError};
use std::sync::{Arc, Mutex};

#[derive(Clone, Copy, Debug)]
enum Command {
    #[cfg(target_os = "windows")]
    TrayAvailability(bool),
    #[cfg(target_os = "windows")]
    ReadFilenameIme(u8),
    Open,
    Close,
    Quit,
    DestroyGraphics,
}

#[derive(Clone)]
struct Control {
    sender: SyncSender<Command>,
    window: Arc<Mutex<Option<Wake>>>,
    #[cfg(target_os = "linux")]
    graphics_attention: Arc<std::sync::atomic::AtomicBool>,
    #[cfg(target_os = "linux")]
    appearance: Arc<Mutex<linux_appearance::Appearance>>,
}

struct Wake {
    context: egui::Context,
    x11: Option<Arc<winit::window::Window>>,
}

impl Control {
    fn send(&self, command: Command) -> Result<(), TrySendError<Command>> {
        self.sender.try_send(command)?;
        self.wake();
        Ok(())
    }

    fn wake(&self) {
        if let Some(wake) = &*self.window.lock().expect("window wake mutex poisoned") {
            if let Some(window) = &wake.x11 {
                window.request_redraw();
                return;
            }
            wake.context.request_repaint();
        }
    }
}

#[derive(Clone, Copy, PartialEq)]
enum ControlId {
    Filename,
    Password,
    Language,
}

struct Model {
    #[cfg(target_os = "windows")]
    ime_sample: Option<u8>,
    #[cfg(windows)]
    foreground: foreground_request::ForegroundRequest,
    #[cfg(windows)]
    root_window: std::sync::Weak<winit::window::Window>,
    lifecycle: DesktopLifecycle,
    commands: Receiver<Command>,
    filename: String,
    password: String,
    german: bool,
    passes: u64,
    graphics: graphics::Graphics,
    last_focus: Option<ControlId>,
    restore_focus: bool,
}

impl Model {
    fn command(&mut self, command: Command) -> Option<HostCommand> {
        let action = match command {
            #[cfg(target_os = "windows")]
            Command::TrayAvailability(available) => self.lifecycle.tray_result(available),
            #[cfg(target_os = "windows")]
            Command::ReadFilenameIme(sample) => {
                self.ime_sample = Some(sample);
                None
            }
            Command::Open => self.lifecycle.activate(),
            Command::Close => self.lifecycle.close_window(),
            Command::Quit => self.lifecycle.request_quit(),
            Command::DestroyGraphics => {
                self.graphics.request_test_fault();
                None
            }
        };
        #[cfg(windows)]
        self.foreground
            .update(matches!(command, Command::Open), action);
        action
    }
}

struct Window {
    model: Rc<RefCell<Model>>,
    control: Control,
    can_hide: bool,
    #[cfg(target_os = "linux")]
    applied_appearance: Option<linux_appearance::Appearance>,
}

impl Window {
    fn new(
        creation: &eframe::CreationContext<'_>,
        model: Rc<RefCell<Model>>,
        control: Control,
    ) -> Self {
        #[cfg(windows)]
        {
            model.borrow_mut().root_window = creation
                .winit_window()
                .map(Arc::downgrade)
                .unwrap_or_default();
            if let Some(root) = creation.winit_window()
                && let Err(error) = windows_appearance::attach(root)
            {
                eprintln!("Windows contrast observation unavailable: {error}");
            }
        }
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
        fonts::add_fallbacks(&mut fonts);
        creation.egui_ctx.set_fonts(fonts);
        model.borrow_mut().graphics.attach(creation);
        if let Some(render) = &creation.wgpu_render_state {
            let info = render.adapter.get_info();
            println!(
                "ADAPTER {:?} {:?} {}",
                info.backend, info.device_type, info.name
            );
        }
        // Winit's X11 backend reports actual visibility and supports unmap/remap. Its
        // Wayland backend reports None and needs a fresh toplevel after a close.
        let can_hide = cfg!(target_os = "linux")
            && creation
                .winit_window()
                .is_some_and(|w| w.is_visible().is_some());
        *control.window.lock().expect("window wake mutex poisoned") = Some(Wake {
            context: creation.egui_ctx.clone(),
            x11: creation.winit_window().filter(|_| can_hide).cloned(),
        });
        if !can_hide {
            creation.egui_ctx.request_repaint();
        }
        Self {
            model,
            control,
            can_hide,
            #[cfg(target_os = "linux")]
            applied_appearance: None,
        }
    }
}

impl Drop for Window {
    fn drop(&mut self) {
        #[cfg(windows)]
        {
            self.model.borrow_mut().root_window = std::sync::Weak::new();
        }
        *self
            .control
            .window
            .lock()
            .expect("window wake mutex poisoned") = None;
    }
}

impl eframe::App for Window {
    fn logic(&mut self, ctx: &egui::Context, frame: &mut eframe::Frame) {
        #[cfg(target_os = "linux")]
        {
            let state = *self
                .control
                .appearance
                .lock()
                .expect("appearance mutex poisoned");
            if self.applied_appearance != Some(state) {
                appearance_style::apply(ctx, state);
                self.applied_appearance = Some(state);
            }
        }
        self.model.borrow_mut().graphics.apply_surface_choice(frame);
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
        if self.can_hide {
            return; // The X11 native event handler owns the top-level controls.
        }
        let mut model = self.model.borrow_mut();
        if ctx.input(|i| i.viewport().close_requested())
            && model.lifecycle.shutdown() == Shutdown::Running
        {
            model.command(Command::Close);
            return;
        }
        while let Ok(command) = model.commands.try_recv() {
            match model.command(command) {
                Some(HostCommand::ShowAndFocus) => {
                    #[cfg(not(windows))]
                    ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
                }
                Some(HostCommand::Hide | HostCommand::StopBackground) => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                    break;
                }
                _ => (),
            }
        }
    }

    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        #[cfg(windows)]
        let palette = windows_appearance::current();
        #[cfg(windows)]
        windows_style::apply(ui, palette);
        let mut model = self.model.borrow_mut();
        model.passes += 1;
        ui.ctx()
            .accesskit_node_builder(egui::accesskit_root_id(), |root| {
                root.set_label("Desktop input probe")
            });
        egui::CentralPanel::default().show(ui, |ui| {
            let de = model.german;
            if let Some(notice) = model.graphics.notice(de) {
                ui.label(notice);
            }
            let label = ui.label(if de { "Dateiname" } else { "Filename" });
            let field = egui::TextEdit::singleline(&mut model.filename);
            #[cfg(windows)]
            let field = windows_style::control(palette, windows_style::TextRole::Window, field);
            let filename = ui.add(field).labelled_by(label.id);
            #[cfg(target_os = "windows")]
            if let Some(sample) = model.ime_sample.take() {
                native_gui_assessment::report_filename_mode(
                    _frame,
                    sample,
                    de && filename.has_focus() && ui.input(|input| input.focused),
                    ui.output(|output| output.ime.is_some()),
                );
            }
            let label = ui.label(if de { "Kennwort" } else { "Password" });
            let field = egui::TextEdit::singleline(&mut model.password).password(true);
            #[cfg(windows)]
            let field = windows_style::control(palette, windows_style::TextRole::Window, field);
            let password = ui.add(field).labelled_by(label.id);
            if password.changed() {
                println!("EDIT masked chars={}", model.password.chars().count());
            }
            let button = egui::Button::new(if de { "English" } else { "Deutsch" });
            #[cfg(windows)]
            let button = windows_style::control(palette, windows_style::TextRole::Button, button);
            let language = ui.add(button);
            if language.clicked() {
                model.german = !de;
            }
            let controls = [
                (ControlId::Filename, filename),
                (ControlId::Password, password),
                (ControlId::Language, language),
            ];
            if model.restore_focus && ui.input(|input| input.focused) {
                if let Some((_, response)) = controls
                    .iter()
                    .find(|(id, _)| Some(*id) == model.last_focus)
                {
                    response.request_focus();
                }
                model.restore_focus = false;
            }
            if let Some((id, _)) = controls.iter().find(|(_, response)| response.has_focus()) {
                model.last_focus = Some(*id);
            }
        });
        model.graphics.finish_ui_for_test();
    }
}

fn supervise(
    model: Rc<RefCell<Model>>,
    control: &Control,
    #[cfg(target_os = "linux")] native: &zbus::Connection,
) -> Result<(), Box<dyn Error>> {
    let mut event_loop = None;
    loop {
        let intent = model.borrow().lifecycle.window_intent();
        if model.borrow().lifecycle.shutdown() != Shutdown::Running {
            break;
        }
        if intent == WindowIntent::Visible {
            let mut options = eframe::NativeOptions {
                viewport: egui::ViewportBuilder::default()
                    .with_title("Desktop input probe")
                    .with_app_id("org.example.IfwGuiProbe")
                    .with_inner_size([640.0, 400.0]),
                renderer: eframe::Renderer::Wgpu,
                persist_window: false,
                run_and_return: true,
                ..Default::default()
            };
            model.borrow_mut().graphics.configure(&mut options);
            let current = Rc::clone(&model);
            let window_control = control.clone();
            let create: eframe::AppCreator<'_> = Box::new(move |ctx| {
                #[cfg(target_os = "linux")]
                linux::graphics_attention(native, &window_control, false);
                Ok(Box::new(Window::new(ctx, current, window_control)))
            });
            let outcome = native_window::run(&mut event_loop, options, create, &model, control);
            let mut model = model.borrow_mut();
            // An internal post-frame eframe exit can leave the model visible despite a dead renderer.
            let failed = model.lifecycle.shutdown() == Shutdown::Running
                && (outcome.is_err()
                    || model.graphics.lost()
                    || model.lifecycle.window_intent() == WindowIntent::Visible);
            if failed {
                model.restore_focus = true;
                println!(
                    "GRAPHICS_ERROR device_lost={} detail={:?}",
                    model.graphics.lost(),
                    outcome.err().map(|e| e.to_string())
                );
            }
            let retry = model.graphics.finish(failed);
            if retry && model.lifecycle.window_intent() == WindowIntent::Visible {
                continue;
            }
            #[cfg(target_os = "linux")]
            if failed && !retry {
                linux::graphics_attention(native, control, true);
            }
            // Some compositors end the window session without a prior CloseRequested event.
            if model.lifecycle.window_intent() == WindowIntent::Visible {
                model.command(Command::Close);
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
        #[cfg(windows)]
        Some("--autostart") if std::env::var("IFW_QA_WINDOWS_LAUNCHER").as_deref() == Ok("1") => {
            true
        }
        None => false,
        _ => return Err("Expected no argument or --background".into()),
    };
    let (sender, commands) = mpsc::sync_channel(8);
    let control = Control {
        sender,
        window: Arc::new(Mutex::new(None)),
        #[cfg(target_os = "linux")]
        graphics_attention: Arc::default(),
        #[cfg(target_os = "linux")]
        appearance: Arc::default(),
    };
    #[cfg(target_os = "linux")]
    let (native, available) = linux::start(control.clone())?;
    #[cfg(target_os = "linux")]
    let mut appearance = {
        let handle = control.clone();
        linux_appearance::Monitor::start(move |state| {
            let mut current = handle.appearance.lock().expect("appearance mutex poisoned");
            if state != *current {
                *current = state;
                drop(current);
                if let Some(wake) = &*handle.window.lock().expect("window wake mutex poisoned") {
                    wake.context.request_repaint();
                }
            }
        })
        .map_err(|error| eprintln!("Desktop appearance unavailable: {error}"))
        .ok()
    };
    #[cfg(target_os = "windows")]
    let mut launcher = {
        let handle = control.clone();
        match native_gui_assessment::start_launcher(move || {
            handle.sender.try_send(Command::Open)?;
            handle.wake();
            Ok(())
        })? {
            native_gui_assessment::Launch::Secondary => return Ok(()),
            native_gui_assessment::Launch::Primary(listener) => Some(listener),
            native_gui_assessment::Launch::Disabled => None,
        }
    };
    #[cfg(target_os = "windows")]
    let mut assessment = benchmark::Benchmark::start()?;
    #[cfg(target_os = "windows")]
    let (mut native, available) = windows_fixture_input(control.clone(), launcher.is_some())?;
    #[cfg(target_os = "windows")]
    assessment.release()?;
    let mut lifecycle = DesktopLifecycle::new(background);
    lifecycle.tray_result(available);
    println!(
        "READY {:?} {:?}",
        lifecycle.window_intent(),
        lifecycle.tray()
    );
    let model = Rc::new(RefCell::new(Model {
        #[cfg(target_os = "windows")]
        ime_sample: None,
        #[cfg(windows)]
        foreground: Default::default(),
        #[cfg(windows)]
        root_window: Default::default(),
        lifecycle,
        commands,
        filename: "Grüße – Sommer.jpg".to_owned(),
        password: String::new(),
        german: true,
        passes: 0,
        graphics: graphics::Graphics::new(),
        last_focus: None,
        restore_focus: false,
    }));
    #[cfg(target_os = "linux")]
    let assessment = benchmark::Benchmark::start()?;
    let result = supervise(
        Rc::clone(&model),
        &control,
        #[cfg(target_os = "linux")]
        &native,
    );
    // Stop admitting window commands when the UI exits. Retain the election through worker drain.
    #[cfg(target_os = "windows")]
    let launcher_stopped = launcher.as_mut().map_or(Ok(()), |listener| listener.stop());
    #[cfg(target_os = "windows")]
    let tray_stopped = native.tray.as_mut().map_or(Ok(()), |tray| tray.stop());
    assessment.finish()?;
    #[cfg(target_os = "windows")]
    launcher_stopped?;
    #[cfg(target_os = "windows")]
    tray_stopped?;
    #[cfg(target_os = "linux")]
    {
        if let Some(observer) = appearance.as_mut() {
            observer.stop()?;
        }
        futures_lite::future::block_on(native.graceful_shutdown());
    }
    #[cfg(target_os = "windows")]
    if result.is_ok() {
        native
            .reader
            .join()
            .map_err(|_| "QA control worker failed")?;
    }
    result?;
    if model.borrow_mut().lifecycle.background_stopped() != Some(HostCommand::ExitEventLoop) {
        return Err("Unexpected supervisor shutdown state".into());
    }
    println!("DRAINED passes={}", model.borrow().passes);
    Ok(())
}

#[cfg(target_os = "windows")]
struct WindowsInput {
    reader: std::thread::JoinHandle<()>,
    tray: Option<native_gui_assessment::NativeTray>,
}

#[cfg(target_os = "windows")]
fn windows_fixture_input(
    control: Control,
    elected: bool,
) -> Result<(WindowsInput, bool), Box<dyn Error>> {
    use native_gui_assessment::{NativeTray, TrayEvent, TrayRequest};
    use std::io::Read;
    let mut input = std::io::stdin();
    let mut next = [0];
    let observe_ime = std::env::var("IFW_QA_FILENAME_IME").as_deref() == Ok("1");
    input.read_exact(&mut next)?;
    let (tray, available) = match std::env::var("IFW_QA_WINDOWS_TRAY").as_deref() {
        Ok("1")
            if next[0] == b'B'
                && elected
                && std::env::var("IFW_QA_BENCHMARK").as_deref() == Ok("1") =>
        {
            // B releases the observer barrier. This process obtains the registration result from the Shell.
            let target = control.clone();
            let (tray, registered) =
                NativeTray::start(std::env::var("IFW_QA_INVENTORY_TOKEN")?, move |event| {
                    target.sender.try_send(match event {
                        TrayEvent::Open => Command::Open,
                        TrayEvent::Availability(available) => Command::TrayAvailability(available),
                    })?;
                    target.wake();
                    Ok(())
                })?;
            (Some(tray), registered)
        }
        Err(std::env::VarError::NotPresent) if next[0] == b'T' || next[0] == b'N' => {
            (None, next[0] == b'T')
        }
        _ => {
            return Err("Expected a tray result or the elected native tray fixture barrier".into());
        }
    };
    let requests = tray.as_ref().map(|owner| owner.requests.clone());
    let handle = std::thread::spawn(move || {
        if let Some(requests) = requests {
            while input.read_exact(&mut next).is_ok() {
                let request = match next[0] {
                    b'M' => TrayRequest::ChangeMarker,
                    b'P' => TrayRequest::Sample,
                    b'Q' => break,
                    _ => continue,
                };
                if requests.send(request).is_err() {
                    break;
                }
            }
            // Only the input reader may wait for a free slot to admit the ordinary Quit.
            if control.sender.send(Command::Quit).is_ok() {
                control.wake();
            }
            return;
        }
        loop {
            let command = match input.read_exact(&mut next) {
                Ok(()) if next[0] == b'O' => Command::Open,
                Ok(()) if next[0] == b'C' => Command::Close,
                Ok(()) if next[0] == b'G' => {
                    if graphics::allows_test_fault() {
                        Command::DestroyGraphics
                    } else {
                        continue;
                    }
                }
                Ok(()) if observe_ime && matches!(next[0], b'1'..=b'7') => {
                    Command::ReadFilenameIme(next[0] - b'0')
                }
                _ => Command::Quit,
            };
            if control.send(command).is_err() || matches!(command, Command::Quit) {
                break;
            }
        }
    });
    Ok((
        WindowsInput {
            reader: handle,
            tray,
        },
        available,
    ))
}
