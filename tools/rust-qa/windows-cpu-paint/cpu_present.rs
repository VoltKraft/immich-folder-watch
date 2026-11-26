//! Direct CPU presentation for the qualified WARP root of the private Windows x64 build.
use std::io::{self, Write as _};
use std::sync::Arc;
use winit::raw_window_handle::{HasWindowHandle as _, RawWindowHandle};
use winit::window::Window;

#[path = "cpu_raster.rs"]
mod cpu_raster;
pub(super) use cpu_raster::PaintError;
#[allow(dead_code)] // The shared DIB module also supports padded GPU copies.
#[path = "dib_layout.rs"]
mod dib_layout;
use dib_layout::{Clip, Layout, Order};

#[repr(C)]
struct BitmapInfo {
    header_bytes: u32,
    width: i32,
    height: i32,
    planes: u16,
    bits: u16,
    compression: u32,
    image_bytes: u32,
    unused: [u32; 4],
    masks: [u32; 3],
}
const _: () = assert!(size_of::<BitmapInfo>() == 52);
#[link(name = "user32")]
unsafe extern "system" {
    fn IsWindowVisible(hwnd: isize) -> i32;
    fn IsIconic(hwnd: isize) -> i32;
    fn GetClientRect(hwnd: isize, rect: *mut [i32; 4]) -> i32;
    fn GetWindowThreadProcessId(hwnd: isize, pid: *mut u32) -> u32;
    fn GetDC(hwnd: isize) -> isize;
    fn ReleaseDC(hwnd: isize, dc: isize) -> i32;
}
#[link(name = "kernel32")]
unsafe extern "system" {
    fn QueryPerformanceCounter(ticks: *mut i64) -> i32;
    fn GetCurrentThreadId() -> u32;
}
#[link(name = "gdi32")]
unsafe extern "system" {
    fn GetClipBox(dc: isize, rect: *mut [i32; 4]) -> i32;
    fn SetDIBitsToDevice(
        dc: isize,
        x: i32,
        y: i32,
        width: u32,
        height: u32,
        sx: i32,
        sy: i32,
        first: u32,
        lines: u32,
        data: *const [u8; 4],
        info: *const BitmapInfo,
        usage: u32,
    ) -> i32;
    fn GdiFlush() -> i32;
}

fn ticks() -> io::Result<i64> {
    let mut value = 0;
    // SAFETY: QueryPerformanceCounter writes one aligned i64.
    if unsafe { QueryPerformanceCounter(&raw mut value) } == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(value)
}
fn visible_size(hwnd: isize) -> io::Result<Option<[u32; 2]>> {
    let mut rect = [0; 4];
    // SAFETY: the caller borrows the Window for the entire paint on its owner thread.
    if unsafe { GetClientRect(hwnd, &raw mut rect) } == 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { IsWindowVisible(hwnd) == 0 || IsIconic(hwnd) != 0 } || rect[2] == 0 || rect[3] == 0
    {
        return Ok(None);
    }
    if rect[0] != 0 || rect[1] != 0 || rect[2] < 0 || rect[3] < 0 {
        return Err(io::Error::other("Invalid root client bounds"));
    }
    Ok(Some([rect[2] as u32, rect[3] as u32]))
}
struct Dc {
    hwnd: isize,
    dc: isize,
}
impl Dc {
    fn new(hwnd: isize) -> io::Result<Self> {
        // SAFETY: the original Window remains borrowed on this thread.
        let dc = unsafe { GetDC(hwnd) };
        if dc == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Self { hwnd, dc })
    }
    fn clip(&self) -> io::Result<Clip> {
        let mut rect = [0; 4];
        let kind = unsafe { GetClipBox(self.dc, &raw mut rect) };
        if !(1..=3).contains(&kind) {
            return Err(io::Error::other("Could not query CPU output clip"));
        }
        Ok(Clip { kind, rect })
    }
    fn close(mut self) -> io::Result<()> {
        let dc = std::mem::take(&mut self.dc);
        if unsafe { ReleaseDC(self.hwnd, dc) } != 1 {
            return Err(io::Error::other("Could not release CPU output DC"));
        }
        Ok(())
    }
}
impl Drop for Dc {
    fn drop(&mut self) {
        if self.dc != 0 {
            unsafe { ReleaseDC(self.hwnd, self.dc) };
        }
    }
}

pub(super) struct Presenter {
    raster: cpu_raster::Raster,
    owner: Option<(isize, u32)>,
    full: u64,
    partial: u64,
}
pub(super) enum Route {
    FirstSurface,
    Cpu(Box<Presenter>),
    Wgpu,
}

impl Route {
    pub(super) fn install(&mut self, state: &crate::RenderState, compatible_root: bool) {
        match self {
            Self::FirstSurface => {
                let info = state.adapter.get_info();
                if compatible_root
                    && matches!(
                        state.target_format,
                        wgpu::TextureFormat::Bgra8Unorm | wgpu::TextureFormat::Rgba8Unorm
                    )
                    && info.backend == wgpu::Backend::Dx12
                    && info.device_type == wgpu::DeviceType::Cpu
                    && info.name == "Microsoft Basic Render Driver"
                {
                    println!("CPU_PAINT_MODE backend=Dx12 device=Cpu selection=adapter");
                    *self = Self::Cpu(Box::new(Presenter {
                        raster: cpu_raster::Raster::new(),
                        owner: None,
                        full: 0,
                        partial: 0,
                    }));
                } else {
                    *self = Self::Wgpu;
                }
            }
            Self::Cpu(_) => self.fallback("surface"),
            Self::Wgpu => {}
        }
    }

    pub(super) fn fallback(&mut self, reason: &'static str) {
        *self = Self::Wgpu;
        println!("CPU_PAINT_FALLBACK reason={reason}");
    }
}

impl Presenter {
    #[expect(clippy::too_many_arguments)]
    pub(super) fn paint(
        &mut self,
        window: &Window,
        size: [u32; 2],
        scale: f32,
        clear: [f32; 4],
        jobs: &[egui::ClippedPrimitive],
        delta: &egui::TexturesDelta,
        capture: bool,
    ) -> Result<(), PaintError> {
        let RawWindowHandle::Win32(raw) =
            window.window_handle().map_err(io::Error::other)?.as_raw()
        else {
            return Err(PaintError::Unsupported("window-handle"));
        };
        let hwnd = raw.hwnd.get();
        let tid = unsafe { GetCurrentThreadId() };
        let mut owner = 0;
        let pid = std::process::id();
        if unsafe { GetWindowThreadProcessId(hwnd, &raw mut owner) } != tid
            || owner != pid
            || *self.owner.get_or_insert((hwnd, tid)) != (hwnd, tid)
        {
            return Err(io::Error::other("CPU paint root HWND or owner changed").into());
        }
        let current = visible_size(hwnd)?;
        if current.is_some_and(|actual| actual != size) {
            return Err(PaintError::Unsupported("dimensions"));
        }
        let dc = current.map(|_| Dc::new(hwnd)).transpose()?;
        let clip = dc.as_ref().map(Dc::clip).transpose()?;
        if dc.is_none() || clip.is_some_and(|c| c.kind == 1) {
            if let Some(dc) = dc {
                dc.close()?;
            }
            // The normal renderer supports screenshot capture even without a drawable surface.
            if capture {
                return Err(PaintError::Unsupported("hidden-capture"));
            }
            if jobs
                .iter()
                .any(|job| matches!(job.primitive, egui::epaint::Primitive::Callback(_)))
            {
                return Err(PaintError::Unsupported("callback"));
            }
            if !delta.is_empty() {
                self.raster.draw(None, clear, &[], delta, scale)?;
            }
            return Ok(());
        }
        let dc = dc.expect("Visible DC");
        let before = clip.expect("Visible clip");
        let [width, height] = size;
        let layout = match Layout::new(width, height, 4) {
            Ok(layout) => layout,
            Err(_) => {
                dc.close()?;
                return Err(PaintError::Unsupported("dimensions"));
            }
        };
        let begin = ticks()?;
        let counts = match self.raster.draw(
            Some([width as usize, height as usize]),
            clear,
            jobs,
            delta,
            scale,
        ) {
            Ok(counts) => counts,
            Err(error) => {
                dc.close()?;
                return Err(error);
            }
        };
        let raster_end = ticks()?;
        let info = BitmapInfo {
            header_bytes: 40,
            width: width as i32,
            height: -(height as i32),
            planes: 1,
            bits: 32,
            compression: 3,
            image_bytes: layout.mapped_bytes,
            unused: [0; 4],
            masks: Order::Bgra.masks(),
        };
        let start = ticks()?;
        // SAFETY: the top-down DIB exactly covers the borrowed BGRA pixel buffer. Its storage
        // remains unchanged through the synchronous transfer, GdiFlush and optional screenshot.
        let lines = unsafe {
            SetDIBitsToDevice(
                dc.dc,
                0,
                0,
                width,
                height,
                0,
                0,
                0,
                height,
                self.raster.pixels.as_ptr(),
                &raw const info,
                0,
            )
        };
        let flushed = unsafe { GdiFlush() } != 0;
        let end = ticks()?;
        let outcome = (|| {
            if !flushed {
                return Err(io::Error::other("Could not flush CPU output"));
            }
            let same = unsafe { GetWindowThreadProcessId(hwnd, &raw mut owner) } == tid
                && owner == pid
                && visible_size(hwnd)? == Some(size);
            dib_layout::complete(lines, before, dc.clip()?, same, layout)
        })();
        let full = match dc.close().and(outcome) {
            Ok(full) => full,
            Err(error) => {
                writeln!(
                    io::stdout().lock(),
                    "GDI_FAILED hwnd={hwnd} tid={tid} start={start} end={end} width={width} height={height} lines={lines} flushed={}",
                    u8::from(flushed)
                )?;
                return Err(error.into());
            }
        };
        let (event, counter) = if full {
            ("GDI_PRESENT", &mut self.full)
        } else {
            ("GDI_PARTIAL", &mut self.partial)
        };
        *counter += 1;
        let mut log = io::stdout().lock();
        writeln!(
            log,
            "{event} frame={counter} hwnd={hwnd} tid={tid} start={start} end={end} width={width} height={height} lines={lines}"
        )?;
        writeln!(
            log,
            "CPU_FRAME seq={} pid={pid} hwnd={hwnd} tid={tid} begin={begin} rasterEnd={raster_end} start={start} end={end} width={width} height={height} meshes={} vertices={} indices={} sets={} frees={} lines={lines} flushed=1",
            self.full + self.partial,
            counts.meshes,
            counts.vertices,
            counts.indices,
            counts.sets,
            counts.frees
        )?;
        Ok(())
    }

    /// Mirror the texture lifetime of the completed frame without acquiring a GPU surface.
    pub(super) fn finish(
        &self,
        state: &crate::RenderState,
        delta: &mut egui::TexturesDelta,
        [width, height]: [u32; 2],
        callbacks: Vec<egui::ScreenshotCallback>,
    ) {
        cpu_raster::finish_frame(
            delta,
            |delta| {
                let mut renderer = state.renderer.write();
                #[expect(clippy::iter_over_hash_type)]
                for (id, changes) in delta.set.drain() {
                    for change in changes {
                        renderer.update_texture(&state.device, &state.queue, id, &change);
                    }
                }
            },
            || {
                state.queue.submit([]);
            },
            |delta| {
                let mut renderer = state.renderer.write();
                #[expect(clippy::iter_over_hash_type)]
                for id in delta.free.drain() {
                    renderer.free_texture(&id);
                }
            },
            || self.complete_screenshots([width, height], callbacks),
        );
    }

    fn complete_screenshots(
        &self,
        [width, height]: [u32; 2],
        callbacks: Vec<egui::ScreenshotCallback>,
    ) {
        if !callbacks.is_empty() {
            let image = Arc::new(egui::ColorImage::new(
                [width as usize, height as usize],
                self.raster
                    .pixels
                    .iter()
                    .map(|p| {
                        let [r, g, b, a] = Order::Bgra.rgba(*p);
                        egui::Color32::from_rgba_premultiplied(r, g, b, a)
                    })
                    .collect(),
            ));
            for callback in callbacks {
                callback.complete(Arc::clone(&image));
            }
        }
    }
}
impl Drop for Presenter {
    fn drop(&mut self) {
        let _ = writeln!(
            io::stdout().lock(),
            "GDI_PRESENT_END frames={} partial={}",
            self.full,
            self.partial
        );
    }
}
