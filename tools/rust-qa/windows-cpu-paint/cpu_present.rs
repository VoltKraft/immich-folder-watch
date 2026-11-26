//! Direct CPU presentation for the explicitly selected private Windows x64 root.
use std::io::{self, Write as _};
use std::sync::Arc;
use winit::raw_window_handle::{HasWindowHandle as _, RawWindowHandle};
use winit::window::Window;

#[path = "cpu_raster.rs"]
mod cpu_raster;
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
fn drawable(hwnd: isize, size: [u32; 2]) -> io::Result<bool> {
    let mut rect = [0; 4];
    // SAFETY: the caller borrows the Window for the entire paint on its owner thread.
    if unsafe { GetClientRect(hwnd, &raw mut rect) } == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { IsWindowVisible(hwnd) != 0 && IsIconic(hwnd) == 0 }
        && size[0] > 0
        && size[1] > 0
        && rect == [0, 0, size[0] as i32, size[1] as i32])
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
impl Presenter {
    pub(super) fn new(
        id: egui::ViewportId,
        adapter: &wgpu::Adapter,
        transparent: bool,
    ) -> Option<Self> {
        if std::env::var("IFW_QA_CPU_PAINT").as_deref() != Ok("1") {
            return None;
        }
        let info = adapter.get_info();
        assert!(
            id == egui::ViewportId::ROOT
                && !transparent
                && std::env::var("IFW_QA_ISOLATED").as_deref() == Ok("1")
                && info.backend == wgpu::Backend::Dx12
                && info.device_type == wgpu::DeviceType::Cpu
                && info.name == "Microsoft Basic Render Driver",
            "CPU painter requires the isolated opaque WARP root"
        );
        writeln!(
            io::stdout().lock(),
            "CPU_PAINT_MODE backend=Dx12 device=Cpu"
        )
        .expect("Could not record CPU paint mode");
        Some(Self {
            raster: cpu_raster::Raster::new(),
            owner: None,
            full: 0,
            partial: 0,
        })
    }

    #[expect(clippy::too_many_arguments)]
    pub(super) fn paint(
        &mut self,
        window: &Window,
        size: [u32; 2],
        scale: f32,
        clear: [f32; 4],
        jobs: &[egui::ClippedPrimitive],
        delta: &mut egui::TexturesDelta,
        callbacks: Vec<egui::ScreenshotCallback>,
    ) -> io::Result<()> {
        let RawWindowHandle::Win32(raw) =
            window.window_handle().map_err(io::Error::other)?.as_raw()
        else {
            return Err(io::Error::other(
                "CPU painter requires the original Win32 root",
            ));
        };
        let hwnd = raw.hwnd.get();
        let tid = unsafe { GetCurrentThreadId() };
        let mut owner = 0;
        let pid = std::process::id();
        if unsafe { GetWindowThreadProcessId(hwnd, &raw mut owner) } != tid
            || owner != pid
            || *self.owner.get_or_insert((hwnd, tid)) != (hwnd, tid)
        {
            return Err(io::Error::other("CPU paint root HWND or owner changed"));
        }
        let dc = drawable(hwnd, size)?.then(|| Dc::new(hwnd)).transpose()?;
        let clip = dc.as_ref().map(Dc::clip).transpose()?;
        if dc.is_none() || clip.is_some_and(|c| c.kind == 1) {
            if !callbacks.is_empty() {
                return Err(io::Error::other("CPU screenshot requires a drawable root"));
            }
            if !delta.is_empty() {
                self.raster.draw(None, clear, &[], delta, scale)?;
            }
            if let Some(dc) = dc {
                dc.close()?;
            }
            return Ok(());
        }
        let dc = dc.expect("Visible DC");
        let before = clip.expect("Visible clip");
        let [width, height] = size;
        let layout = Layout::new(width, height, 4)?;
        let begin = ticks()?;
        let counts = self.raster.draw(
            Some([width as usize, height as usize]),
            clear,
            jobs,
            delta,
            scale,
        )?;
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
                && drawable(hwnd, size)?;
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
                return Err(error);
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
        drop(log);
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
        Ok(())
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
