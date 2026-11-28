//! A local native parent window and portal caller for a synthetic session.
#![deny(unsafe_op_in_unsafe_fn)]

mod display_path;
mod document_uri;
mod parent;
mod portal;

use parent::Parent;
use std::error::Error;
use std::sync::Arc;
use winit::application::ApplicationHandler;
use winit::dpi::LogicalSize;
use winit::event::WindowEvent;
use winit::event_loop::{ActiveEventLoop, EventLoop, EventLoopProxy};
use winit::window::{Window, WindowId};

type Outcome = Result<(), String>;
struct Application {
    action: String,
    proxy: EventLoopProxy<Outcome>,
    parent: Option<Parent>,
    window: Option<Arc<Window>>,
    result: Option<Outcome>,
    worker: Option<std::thread::JoinHandle<()>>,
}

impl Application {
    fn fail(&mut self, events: &ActiveEventLoop, error: impl ToString) {
        self.result = Some(Err(error.to_string()));
        events.exit();
    }
}
impl ApplicationHandler<Outcome> for Application {
    fn resumed(&mut self, events: &ActiveEventLoop) {
        if self.window.is_some() {
            return;
        }
        let attributes = Window::default_attributes()
            .with_title("Synthetic native portal parent")
            .with_inner_size(LogicalSize::new(640.0, 430.0));
        match events.create_window(attributes) {
            Ok(window) => {
                window.request_redraw();
                self.window = Some(Arc::new(window));
            }
            Err(error) => self.fail(events, error),
        }
    }
    fn window_event(&mut self, events: &ActiveEventLoop, _: WindowId, event: WindowEvent) {
        if event == WindowEvent::CloseRequested {
            self.fail(events, "Parent closed before portal response");
            return;
        }
        if event != WindowEvent::RedrawRequested || self.parent.is_some() {
            return;
        }
        let Some(window) = self.window.as_ref() else {
            return;
        };
        match Parent::new(Arc::clone(window)) {
            Ok(parent) => {
                println!("PARENT {}", parent.id);
                let handle = parent.id.clone();
                self.parent = Some(parent);
                let action = self.action.clone();
                let queue = self.proxy.clone();
                self.worker = Some(std::thread::spawn(move || {
                    let result = futures_lite::future::block_on(portal::run(&action, &handle))
                        .map_err(|e| e.to_string());
                    let _ = queue.send_event(result);
                }));
            }
            Err(error) => self.fail(events, error),
        }
    }
    fn user_event(&mut self, events: &ActiveEventLoop, result: Outcome) {
        self.result = Some(result);
        events.exit();
    }
    fn exiting(&mut self, _: &ActiveEventLoop) {
        self.parent.take();
        self.window.take();
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    if std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1") {
        return Err("Use the isolated portal assessment launcher".into());
    }
    if std::path::Path::new("/tmp/selection").try_exists()? {
        return Err("The portal client could see the private producer path".into());
    }
    let action = std::env::args().nth(1).ok_or("Missing portal action")?;
    if std::path::Path::new("/.flatpak-info").is_file() {
        let id = std::env::var("FLATPAK_ID")?;
        if id != portal::APP {
            return Err("Unexpected installed Flatpak identity".into());
        }
        println!("APPLICATION_FLATPAK {id}");
        if action == "reopen-saved" {
            let path = std::env::args_os()
                .nth(2)
                .ok_or("Missing saved folder path")?;
            let check_fallback = std::env::args_os().nth(3).as_deref()
                == Some(std::ffi::OsStr::new("--observe-portal"));
            return futures_lite::future::block_on(portal::reopen_saved(
                std::path::Path::new(&path),
                check_fallback,
            ));
        }
        if action == "recheck-revoked" {
            let uri = std::env::args()
                .nth(2)
                .ok_or("Missing revoked document URI")?;
            let grant = document_uri::parse(&uri, &portal::documents_mount()?)?;
            if let Some(still_granted) = std::env::args().nth(3) {
                portal::inspect_grant(&still_granted)?;
            }
            return match grant.open() {
                Err(error)
                    if matches!(
                        error.kind(),
                        std::io::ErrorKind::NotFound | std::io::ErrorKind::PermissionDenied
                    ) =>
                {
                    println!("GRANT_REVOKED errno={:?}", error.raw_os_error());
                    Ok(())
                }
                _ => Err(
                    "Revoked directory remained accessible or returned an unexpected error".into(),
                ),
            };
        }
    }
    if matches!(action.as_str(), "notify" | "withdraw") {
        return futures_lite::future::block_on(portal::run(&action, ""));
    }
    let events = EventLoop::<Outcome>::with_user_event().build()?;
    let mut app = Application {
        action,
        proxy: events.create_proxy(),
        parent: None,
        window: None,
        result: None,
        worker: None,
    };
    events.run_app(&mut app)?;
    if let Some(worker) = app.worker.take() {
        worker.join().map_err(|_| "Portal worker panicked")?;
    }
    app.result.ok_or("Event loop ended without an outcome")??;
    Ok(())
}
