//! Present a rendered root frame from the DX12 CPU adapter through the owning window's DC.
use core::ffi::c_void;
use core::time::Duration;
use std::io::{self, Write as _};
use std::sync::{Arc, mpsc};
use winit::raw_window_handle::{HasWindowHandle as _, RawWindowHandle};
use winit::window::Window;

#[path = "dib_layout.rs"]
mod dib_layout;
use dib_layout::{Clip, Layout, Order};

#[repr(C)]
struct BitmapInfo {
    header_bytes: u32,
    width: i32,
    height: i32,
    planes: u16,
    bit_count: u16,
    compression: u32,
    size_image: u32,
    x_pixels_per_m: i32,
    y_pixels_per_m: i32,
    colors_used: u32,
    colors_important: u32,
    masks: [u32; 3],
}
const _: () = assert!(
    core::mem::size_of::<BitmapInfo>() == 52,
    "Unexpected Win32 DIB layout"
);

#[link(name = "user32")]
unsafe extern "system" {
    fn GetDC(hwnd: isize) -> isize;
    fn ReleaseDC(hwnd: isize, dc: isize) -> i32;
    fn GetWindowThreadProcessId(hwnd: isize, pid: *mut u32) -> u32;
}
#[link(name = "gdi32")]
unsafe extern "system" {
    fn SetDIBitsToDevice(
        dc: isize,
        x: i32,
        y: i32,
        width: u32,
        height: u32,
        src_x: i32,
        src_y: i32,
        first_line: u32,
        lines: u32,
        bits: *const c_void,
        info: *const BitmapInfo,
        usage: u32,
    ) -> i32;
    fn GdiFlush() -> i32;
    fn GetClipBox(dc: isize, rect: *mut [i32; 4]) -> i32;
}
#[link(name = "kernel32")]
unsafe extern "system" {
    fn QueryPerformanceCounter(ticks: *mut i64) -> i32;
    fn GetCurrentThreadId() -> u32;
}

pub(super) fn selected(id: egui::ViewportId, adapter: &wgpu::Adapter, transparent: bool) -> bool {
    if id != egui::ViewportId::ROOT
        || transparent
        || std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
        || std::env::var("IFW_QA_WINDOWS_GDI_PRESENT").as_deref() != Ok("1")
    {
        return false;
    }
    let info = adapter.get_info();
    if info.backend != wgpu::Backend::Dx12
        || info.device_type != wgpu::DeviceType::Cpu
        || info.name != "Microsoft Basic Render Driver"
    {
        return false;
    }
    writeln!(
        io::stdout().lock(),
        "GDI_PRESENT_MODE backend=Dx12 device=Cpu"
    )
    .expect("Could not record the selected GDI mode");
    true
}

pub(super) fn check_size(width: u32, height: u32) -> io::Result<()> {
    Layout::new(width, height, wgpu::COPY_BYTES_PER_ROW_ALIGNMENT).map(|_| ())
}

fn ticks() -> io::Result<i64> {
    let mut value = 0;
    // SAFETY: the large integer output is aligned and writable throughout the call.
    if unsafe { QueryPerformanceCounter(&raw mut value) } == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(value)
}

struct WindowDc {
    hwnd: isize,
    dc: isize,
}

impl Drop for WindowDc {
    fn drop(&mut self) {
        if self.dc != 0 {
            // SAFETY: an early error still owns its common DC on the acquiring thread.
            unsafe { ReleaseDC(self.hwnd, self.dc) };
        }
    }
}

impl WindowDc {
    fn clip(&self) -> io::Result<Clip> {
        let mut rect = [0; 4];
        // SAFETY: RECT comprises four signed 32-bit integers and self owns its live DC.
        let kind = unsafe { GetClipBox(self.dc, &raw mut rect) };
        if !(1..=3).contains(&kind) {
            return Err(io::Error::other("Could not query the GDI clip"));
        }
        Ok(Clip { kind, rect })
    }

    fn close(mut self) -> io::Result<()> {
        let dc = core::mem::take(&mut self.dc);
        // SAFETY: winit's window class uses a common DC; this is its single release.
        if unsafe { ReleaseDC(self.hwnd, dc) } != 1 {
            return Err(io::Error::other("Could not release the window DC"));
        }
        Ok(())
    }
}

fn visible_size(window: &Window, layout: Layout) -> bool {
    let size = window.inner_size();
    window.is_visible() == Some(true)
        && window.is_minimized() != Some(true)
        && (size.width, size.height) == (layout.width, layout.height)
}

fn window_hwnd(window: &Window) -> io::Result<isize> {
    match window.window_handle().map_err(io::Error::other)?.as_raw() {
        RawWindowHandle::Win32(raw) => Ok(raw.hwnd.get()),
        _ => Err(io::Error::other("GDI root requires a Win32 window")),
    }
}

fn blit(
    window: &Window,
    layout: Layout,
    order: Order,
    source: &[u8],
    frames: &mut super::GdiFrames,
) -> io::Result<()> {
    if !visible_size(window, layout) {
        // A hidden initial viewport is shown by eframe after its first pass. Normal
        // WM_PAINT and resize events render the next visible frame at its current size.
        return Ok(());
    }
    let hwnd = window_hwnd(window)?;
    // SAFETY: the borrowed Window is retained until its DC and image copy are finished.
    let tid = unsafe { GetCurrentThreadId() };
    if unsafe { GetWindowThreadProcessId(hwnd, core::ptr::null_mut()) } != tid {
        return Err(io::Error::other(
            "GDI frame reached a different window thread",
        ));
    }
    let dc = unsafe { GetDC(hwnd) };
    if dc == 0 {
        return Err(io::Error::last_os_error());
    }
    let target = WindowDc { hwnd, dc };
    let before = target.clip()?;
    if before.kind == 1 {
        return target.close(); // NULLREGION, including a transient occlusion.
    }
    let info = BitmapInfo {
        header_bytes: 40,
        // A DIB row contains the copy padding. The source rectangle selects only the
        // actual client width. A negative height preserves wgpu's top-down row order.
        width: (layout.row_bytes / 4) as i32,
        height: -(layout.height as i32),
        planes: 1,
        bit_count: 32,
        compression: 3, // BI_BITFIELDS
        size_image: layout.mapped_bytes,
        x_pixels_per_m: 0,
        y_pixels_per_m: 0,
        colors_used: 0,
        colors_important: 0,
        masks: order.masks(),
    };
    let start = ticks()?;
    // SAFETY: the pinned mapped slice contains the complete padded DIB. No mutable
    // access is possible during this transfer. Flush precedes releasing the mapping.
    let lines = unsafe {
        SetDIBitsToDevice(
            target.dc,
            0,
            0,
            layout.width,
            layout.height,
            0,
            0,
            0,
            layout.height,
            source.as_ptr().cast(),
            &raw const info,
            0,
        )
    };
    let flushed = unsafe { GdiFlush() } != 0;
    let end = ticks()?;
    // Include an attempt when the drawable becomes occluded or resizes during a
    // flush, while reserving full-frame evidence for stable client and clip bounds.
    let after = target.clip();
    let same_window = window_hwnd(window).ok() == Some(hwnd)
        && unsafe { GetWindowThreadProcessId(hwnd, core::ptr::null_mut()) } == tid
        && visible_size(window, layout);
    let outcome = target.close().and_then(|()| {
        if !flushed {
            return Err(io::Error::other("Could not flush the GDI frame"));
        }
        dib_layout::complete(lines, before, after?, same_window, layout)
    });
    let (event, count) = match outcome {
        Ok(true) => ("GDI_PRESENT", &mut frames.full),
        Ok(false) => ("GDI_PARTIAL", &mut frames.partial),
        Err(error) => {
            writeln!(
                io::stdout().lock(),
                "GDI_FAILED hwnd={hwnd} tid={tid} start={start} end={end} width={} height={} lines={lines} flushed={}",
                layout.width,
                layout.height,
                u8::from(flushed)
            )?;
            return Err(error);
        }
    };
    *count = count
        .checked_add(1)
        .ok_or_else(|| io::Error::other("GDI frame counter exhausted"))?;
    writeln!(
        io::stdout().lock(),
        "{event} frame={count} hwnd={hwnd} tid={tid} start={start} end={end} width={} height={} lines={lines}",
        layout.width,
        layout.height
    )
}

pub(super) struct Readback {
    pub device: wgpu::Device,
    pub submission: wgpu::SubmissionIndex,
    pub buffer: wgpu::Buffer,
    pub size: [u32; 2],
    pub format: wgpu::TextureFormat,
}

impl Readback {
    pub fn present(
        self,
        window: &Window,
        frames: &mut super::GdiFrames,
        callbacks: Vec<egui::ScreenshotCallback>,
    ) -> io::Result<()> {
        let [width, height] = self.size;
        let layout = Layout::new(width, height, wgpu::COPY_BYTES_PER_ROW_ALIGNMENT)?;
        let order = match self.format {
            wgpu::TextureFormat::Bgra8Unorm => Order::Bgra,
            wgpu::TextureFormat::Rgba8Unorm => Order::Rgba,
            _ => return Err(io::Error::other("Unsupported GDI root texture format")),
        };
        if self.buffer.size() != u64::from(layout.mapped_bytes) {
            return Err(io::Error::other(
                "GDI buffer does not match the padded frame",
            ));
        }
        let slice = self.buffer.slice(..);
        let (done, result) = mpsc::sync_channel(1);
        slice.map_async(wgpu::MapMode::Read, move |status| {
            let _ = done.try_send(status);
        });
        // Only one readback owns this UI thread at a time. No later frame can replace
        // its size, HWND or generation. A bounded failure aborts the diagnostic.
        self.device
            .poll(wgpu::PollType::Wait {
                submission_index: Some(self.submission),
                timeout: Some(Duration::from_secs(2)),
            })
            .map_err(io::Error::other)?;
        result
            .try_recv()
            .map_err(io::Error::other)?
            .map_err(io::Error::other)?;
        let mapped = slice.get_mapped_range().map_err(io::Error::other)?;
        let draw = blit(window, layout, order, &mapped, frames);
        // Ordinary screenshot requests receive the same premultiplied RGBA pixels as
        // CaptureState::read_screen_rgba, including for a currently hidden root.
        let screenshot = (!callbacks.is_empty()).then(|| {
            let pixels = mapped
                .chunks_exact(layout.row_bytes as usize)
                .flat_map(|row| {
                    row[..width as usize * 4]
                        .as_chunks::<4>()
                        .0
                        .iter()
                        .map(|pixel| {
                            let [r, g, b, a] = order.rgba(*pixel);
                            epaint::Color32::from_rgba_premultiplied(r, g, b, a)
                        })
                })
                .collect();
            Arc::new(epaint::ColorImage::new(
                [width as usize, height as usize],
                pixels,
            ))
        });
        drop(mapped);
        self.buffer.unmap();
        if let Some(image) = screenshot {
            for callback in callbacks {
                callback.complete(Arc::clone(&image));
            }
        }
        draw
    }
}
