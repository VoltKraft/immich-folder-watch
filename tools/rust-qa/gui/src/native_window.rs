//! Dispatch native close on the UI thread before scheduling any additional compositor frame.
use super::{Control, HostCommand, Model, Shutdown, WindowIntent};
use std::cell::RefCell;
use std::error::Error;
use std::sync::Arc;
use winit::application::ApplicationHandler;
use winit::event::{DeviceEvent, DeviceId, Ime, StartCause, WindowEvent};
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop};
use winit::platform::run_on_demand::EventLoopExtRunOnDemand;
use winit::window::{Window, WindowId};

struct Handler<'a> {
    eframe: eframe::EframeWinitApplication<'a>,
    model: &'a RefCell<Model>,
    control: &'a Control,
    initial_pass: u64,
    mapping_events: Vec<WindowEvent>,
    repaint_after_map: bool,
}

impl Handler<'_> {
    fn x11_root(&self) -> Option<Arc<Window>> {
        self.control
            .window
            .lock()
            .expect("window wake mutex poisoned")
            .as_ref()
            .and_then(|wake| wake.x11.as_ref())
            .cloned()
    }

    fn hide(window: &Window) {
        window.set_visible(false);
        println!("WINDOW_HIDDEN");
    }

    fn controls_allow_redraw(&self, event_loop: &ActiveEventLoop, window: &Window) -> bool {
        let mut model = self.model.borrow_mut();
        while let Ok(command) = model.commands.try_recv() {
            match model.command(command) {
                Some(HostCommand::ShowAndFocus) => {
                    window.set_visible(true);
                    window.focus_window();
                }
                Some(HostCommand::Hide) => Self::hide(window),
                Some(HostCommand::StopBackground) => {
                    event_loop.exit();
                    return false;
                }
                _ => (),
            }
        }
        model.lifecycle.window_intent() == WindowIntent::Visible
    }

    fn flush_mapping(&mut self, event_loop: &ActiveEventLoop, window: &Window) {
        for event in self.mapping_events.drain(..) {
            self.eframe.window_event(event_loop, window.id(), event);
        }
        if std::mem::take(&mut self.repaint_after_map) {
            window.request_redraw();
        }
    }
}

impl ApplicationHandler<eframe::UserEvent> for Handler<'_> {
    fn window_event(&mut self, event_loop: &ActiveEventLoop, id: WindowId, event: WindowEvent) {
        if let Some(window) = self.x11_root().filter(|window| window.id() == id) {
            match event {
                WindowEvent::CloseRequested => {
                    if self.model.borrow_mut().lifecycle.close_window() == Some(HostCommand::Hide) {
                        Self::hide(&window);
                        return;
                    }
                }
                WindowEvent::RedrawRequested
                    if !self.controls_allow_redraw(event_loop, &window) =>
                {
                    return;
                }
                _ => (),
            }
            // Winit marks a mapped X11 window visible after returning from its Occluded callback.
            // Before that acknowledgement eframe paints and sleeps synchronously on each of these
            // notifications. Preserve their order, then dispatch once X11 can schedule normal frames.
            if self.model.borrow().passes > self.initial_pass && window.is_visible() == Some(false)
            {
                match event {
                    WindowEvent::RedrawRequested => {
                        self.repaint_after_map = true;
                        return;
                    }
                    WindowEvent::Focused(_)
                    | WindowEvent::Occluded(_)
                    | WindowEvent::Resized(_)
                    | WindowEvent::Ime(Ime::Enabled | Ime::Disabled)
                        if self.mapping_events.len() < 8 =>
                    {
                        self.mapping_events.push(event);
                        return;
                    }
                    _ => (),
                }
            }
            self.flush_mapping(event_loop, &window);
        }
        self.eframe.window_event(event_loop, id, event);
    }

    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        self.eframe.resumed(event_loop);
    }
    fn new_events(&mut self, event_loop: &ActiveEventLoop, cause: StartCause) {
        self.eframe.new_events(event_loop, cause);
    }
    fn user_event(&mut self, event_loop: &ActiveEventLoop, event: eframe::UserEvent) {
        self.eframe.user_event(event_loop, event);
    }
    fn device_event(&mut self, event_loop: &ActiveEventLoop, id: DeviceId, event: DeviceEvent) {
        self.eframe.device_event(event_loop, id, event);
    }
    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        if let Some(window) = self.x11_root().filter(|w| w.is_visible() == Some(true)) {
            self.flush_mapping(event_loop, &window);
        }
        self.eframe.about_to_wait(event_loop);
    }
    fn suspended(&mut self, event_loop: &ActiveEventLoop) {
        self.eframe.suspended(event_loop);
    }
    fn exiting(&mut self, event_loop: &ActiveEventLoop) {
        self.eframe.exiting(event_loop);
    }
    fn memory_warning(&mut self, event_loop: &ActiveEventLoop) {
        self.eframe.memory_warning(event_loop);
    }
}

pub(super) fn run<'a>(
    event_loop: &mut Option<EventLoop<eframe::UserEvent>>,
    options: eframe::NativeOptions,
    create: eframe::AppCreator<'a>,
    model: &'a RefCell<Model>,
    control: &'a Control,
) -> Result<(), Box<dyn Error>> {
    let event_loop = match event_loop {
        Some(existing) => existing,
        empty => empty.insert(EventLoop::with_user_event().build()?),
    };
    event_loop.set_control_flow(ControlFlow::Wait);
    let passes_before = model.borrow().passes;
    let app = eframe::create_native("Desktop input probe", options, create, event_loop);
    let mut handler = Handler {
        eframe: app,
        model,
        control,
        initial_pass: passes_before,
        mapping_events: Vec::new(),
        repaint_after_map: false,
    };
    event_loop.run_app_on_demand(&mut handler)?;
    let model = model.borrow();
    if model.passes == passes_before
        && model.lifecycle.shutdown() == Shutdown::Running
        && model.lifecycle.window_intent() == WindowIntent::Visible
    {
        return Err("Native renderer exited before its first UI pass".into());
    }
    Ok(())
}
