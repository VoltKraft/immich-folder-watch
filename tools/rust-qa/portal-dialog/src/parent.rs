//! Tie the xdg-foreign export and the display borrowed by libwayland to the owned winit window.

use raw_window_handle::{HasDisplayHandle, HasWindowHandle, RawDisplayHandle, RawWindowHandle};
use std::fs::File;
use std::io::{Seek, SeekFrom, Write};
use std::os::fd::AsFd;
use std::sync::Arc;
use wayland_backend::client::{Backend, ObjectId};
use wayland_client::globals::{GlobalList, GlobalListContents, registry_queue_init};
use wayland_client::protocol::{
    wl_buffer, wl_registry, wl_shm, wl_shm_pool, wl_surface::WlSurface,
};
use wayland_client::{Connection, Dispatch, EventQueue, Proxy, QueueHandle, delegate_noop};
use wayland_protocols::xdg::foreign::zv2::client::{zxdg_exported_v2, zxdg_exporter_v2};
use winit::window::Window;

type Failure = Box<dyn std::error::Error>;

#[derive(Default)]
struct QueueState {
    exported_handle: Option<String>,
}
impl Dispatch<wl_registry::WlRegistry, GlobalListContents> for QueueState {
    fn event(
        _: &mut Self,
        _: &wl_registry::WlRegistry,
        _: wl_registry::Event,
        _: &GlobalListContents,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
    }
}
delegate_noop!(QueueState: ignore wl_shm::WlShm);
delegate_noop!(QueueState: ignore wl_shm_pool::WlShmPool);
delegate_noop!(QueueState: ignore wl_buffer::WlBuffer);
delegate_noop!(QueueState: ignore zxdg_exporter_v2::ZxdgExporterV2);

impl Dispatch<zxdg_exported_v2::ZxdgExportedV2, ()> for QueueState {
    fn event(
        state: &mut Self,
        _: &zxdg_exported_v2::ZxdgExportedV2,
        event: zxdg_exported_v2::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        if let zxdg_exported_v2::Event::Handle { handle } = event {
            state.exported_handle = Some(handle);
        }
    }
}

struct Export {
    exported: zxdg_exported_v2::ZxdgExportedV2,
    exporter: zxdg_exporter_v2::ZxdgExporterV2,
    buffer: wl_buffer::WlBuffer,
    globals: Option<GlobalList>,
    _queue: EventQueue<QueueState>,
    connection: Connection,
}

impl Drop for Export {
    fn drop(&mut self) {
        self.exported.destroy();
        self.exporter.destroy();
        self.buffer.destroy();
        if let Some(globals) = self.globals.take() {
            globals.destroy();
        }
        let _ = self.connection.flush();
    }
}

pub struct Parent {
    pub id: String,
    // Fields drop in declaration order. The foreign backend and export always drop before the window.
    _export: Option<Export>,
    _window: Arc<Window>,
}

impl Parent {
    pub fn new(window: Arc<Window>) -> Result<Self, Failure> {
        let display = window.display_handle()?.as_raw();
        let handle = window.window_handle()?.as_raw();
        let (id, export) = match (display, handle) {
            (_, RawWindowHandle::Xlib(w)) => (format!("x11:{:x}", w.window), None),
            (_, RawWindowHandle::Xcb(w)) => (format!("x11:{:x}", w.window), None),
            (RawDisplayHandle::Wayland(d), RawWindowHandle::Wayland(w)) => {
                // Both handles come from this same live window on the event-loop thread. The
                // strong window reference outlives every guest proxy and backend in Export. The
                // guest neither disconnects libwayland nor takes ownership of winit's wl_surface.
                let backend = unsafe { Backend::from_foreign_display(d.display.as_ptr().cast()) };
                // The interface is exactly wl_surface as guaranteed by the Wayland raw window handle.
                let surface_id = unsafe {
                    ObjectId::from_ptr(WlSurface::interface(), w.surface.as_ptr().cast())
                }?;
                let connection = Connection::from_backend(backend);
                let surface = WlSurface::from_id(&connection, surface_id)?;
                let (globals, mut queue) = registry_queue_init::<QueueState>(&connection)?;
                let q = queue.handle();
                let exporter: zxdg_exporter_v2::ZxdgExporterV2 = globals.bind(&q, 1..=1, ())?;
                let shm: wl_shm::WlShm = globals.bind(&q, 1..=1, ())?;
                // A mapped parent needs an attached buffer. Use a plain, unlinked synthetic
                // backing file. This fixture exercises native parenting independently of a renderer.
                let size = window.inner_size();
                let width = i32::try_from(size.width.clamp(1, 1600))?;
                let height = i32::try_from(size.height.clamp(1, 1000))?;
                let stride = width * 4;
                let length = stride * height;
                let backing =
                    std::env::temp_dir().join(format!("ifw-dialog-pixels-{}", std::process::id()));
                let mut file = File::create_new(&backing)?;
                std::fs::remove_file(backing)?;
                file.write_all(&[0x41, 0x55, 0x2d, 0xff].repeat(usize::try_from(length / 4)?))?;
                file.seek(SeekFrom::Start(0))?;
                let pool = shm.create_pool(file.as_fd(), length, &q, ());
                let buffer =
                    pool.create_buffer(0, width, height, stride, wl_shm::Format::Argb8888, &q, ());
                pool.destroy();
                window.pre_present_notify();
                surface.attach(Some(&buffer), 0, 0);
                surface.damage(0, 0, width, height);
                surface.commit();
                let exported = exporter.export_toplevel(&surface, &q, ());
                let mut state = QueueState::default();
                queue.roundtrip(&mut state)?;
                let raw = state
                    .exported_handle
                    .filter(|s| !s.is_empty() && s.len() <= 512 && !s.contains('\0'))
                    .ok_or("Compositor supplied no usable xdg-foreign handle")?;
                (
                    format!("wayland:{raw}"),
                    Some(Export {
                        exported,
                        exporter,
                        buffer,
                        globals: Some(globals),
                        _queue: queue,
                        connection,
                    }),
                )
            }
            _ => return Err("Unsupported native parent".into()),
        };
        Ok(Self {
            id,
            _export: export,
            _window: window,
        })
    }
}
