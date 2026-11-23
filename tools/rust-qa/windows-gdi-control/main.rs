//! Isolated 640 by 400 Win32 DIB and visibility control for the measured inventory worker.
#![windows_subsystem = "windows"]
use std::cell::RefCell;
use std::ffi::c_void;
use std::io::{self, Read, Write};
use std::ptr;
use std::thread;

mod win32;
#[path = "../gui/src/windows_worker.rs"]
mod windows_worker;
use win32::*;

const WIDTH: i32 = 640;
const HEIGHT: i32 = 400;
const STYLE: u32 = 0x00cf0000; // WS_OVERLAPPEDWINDOW
const CONTROL: u32 = 0x8001; // private thread message
const OPEN: usize = b'O' as usize;
const QUIT: usize = b'Q' as usize;
const MAX_GENERATIONS: u32 = 20_000;
thread_local! { static FRAME: RefCell<Option<Frame>> = const { RefCell::new(None) }; }

fn checked(success: i32) -> io::Result<()> {
    if success == 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

fn ticks() -> io::Result<i64> {
    let mut value = 0;
    // The Windows LARGE_INTEGER output is one signed 64-bit value.
    checked(unsafe { QueryPerformanceCounter(&mut value) })?;
    Ok(value)
}

struct Frame {
    dc: Handle,
    bitmap: Handle,
    original: Handle,
    pixels: *mut u32,
    seed: u32,
    generation: u32,
    reported: u32,
}

impl Frame {
    fn new(seed: u32) -> io::Result<Self> {
        let mut info = BitmapInfo::default();
        info.header.size = size_of::<BitmapHeader>() as u32;
        info.header.width = WIDTH;
        info.header.height = -HEIGHT; // top-down, 32-bit BI_RGB
        info.header.planes = 1;
        info.header.bits = 32;
        let mut pixels: *mut c_void = ptr::null_mut();
        // The GUI thread owns this private DC and its only selected bitmap until Drop.
        unsafe {
            let dc = CreateCompatibleDC(0);
            if dc == 0 {
                return Err(io::Error::last_os_error());
            }
            let bitmap = CreateDIBSection(dc, &info, 0, &mut pixels, 0, 0);
            let original = if bitmap == 0 || pixels.is_null() {
                0
            } else {
                SelectObject(dc, bitmap)
            };
            if original == 0 || original == -1 {
                let error = io::Error::last_os_error();
                DeleteDC(dc);
                if bitmap != 0 {
                    DeleteObject(bitmap);
                }
                return Err(error);
            }
            Ok(Self {
                dc,
                bitmap,
                original,
                pixels: pixels.cast(),
                seed,
                generation: 0,
                reported: 0,
            })
        }
    }

    fn advance(&mut self) -> io::Result<()> {
        if self.generation >= MAX_GENERATIONS {
            return Err(io::Error::other("Frame generation limit exceeded"));
        }
        self.generation += 1;
        let color = self.color();
        // The fixed DIB has WIDTH*HEIGHT complete u32 pixels. Each previous copy was flushed
        // before its bits could be rewritten on this thread.
        let pixels =
            unsafe { std::slice::from_raw_parts_mut(self.pixels, (WIDTH * HEIGHT) as usize) };
        let (top, bottom) = pixels.split_at_mut(pixels.len() / 2);
        top.fill(color);
        bottom.fill(color ^ 0xffffff);
        Ok(())
    }

    fn color(&self) -> u32 {
        self.seed
            .wrapping_add(self.generation.wrapping_mul(0x5bc189))
            & 0xffffff
    }

    fn paint(&mut self, hwnd: Handle, destination: Handle) -> io::Result<()> {
        let mut rect = Rect::default();
        let start;
        // The BeginPaint HDC and DIB are live on the owning thread for the full transfer.
        unsafe {
            checked(GetClientRect(hwnd, &mut rect))?;
            if (rect.right, rect.bottom) != (WIDTH, HEIGHT) {
                return Err(io::Error::other("Unexpected client size"));
            }
            start = ticks()?;
            checked(BitBlt(
                destination,
                0,
                0,
                WIDTH,
                HEIGHT,
                self.dc,
                0,
                0,
                0x00cc0020,
            ))?;
            checked(GdiFlush())?;
        }
        let end = ticks()?;
        if self.generation != self.reported {
            writeln!(
                io::stdout().lock(),
                "GDI_FRAME {hwnd} {} {start} {end} {:06x}",
                self.generation,
                self.color()
            )?;
            self.reported = self.generation;
        }
        Ok(())
    }
}

impl Drop for Frame {
    fn drop(&mut self) {
        // A bitmap must be deselected before deletion. No other thread uses this DC.
        unsafe {
            SelectObject(self.dc, self.original);
            DeleteDC(self.dc);
            DeleteObject(self.bitmap);
        }
    }
}

fn in_frame<R>(f: impl FnOnce(&mut Frame) -> io::Result<R>) -> io::Result<R> {
    FRAME.with(|slot| {
        f(slot
            .try_borrow_mut()
            .map_err(|_| io::Error::other("Reentered GDI frame"))?
            .as_mut()
            .ok_or_else(|| io::Error::other("Missing DIB"))?)
    })
}

fn visibility(hwnd: Handle, show: bool) -> io::Result<()> {
    let generation = in_frame(|frame| Ok(frame.generation))?;
    // ShowWindow may synchronously deliver messages. No Rust frame borrow is held.
    let before = unsafe { IsWindowVisible(hwnd) } != 0;
    let start = ticks()?;
    unsafe { ShowWindow(hwnd, if show { 5 } else { 0 }) }; // SW_SHOW / SW_HIDE
    let end = ticks()?;
    let after = unsafe { IsWindowVisible(hwnd) } != 0;
    if before == show || after != show {
        return Err(io::Error::other(
            "Unexpected native visibility before or after ShowWindow",
        ));
    }
    writeln!(
        io::stdout().lock(),
        "GDI_VISIBILITY {hwnd} {generation} {} {start} {end}",
        if show { "show" } else { "hide" }
    )
}

extern "system" fn procedure(hwnd: Handle, message: u32, wp: usize, lp: isize) -> isize {
    // Windows supplied the class's live HWND. BeginPaint/EndPaint are paired even on errors.
    unsafe {
        match message {
            0x0010 => {
                if visibility(hwnd, false).is_err() {
                    PostQuitMessage(1);
                }
            } // WM_CLOSE
            0x000f => {
                // WM_PAINT
                let mut paint = Paint::default();
                let dc = BeginPaint(hwnd, &mut paint);
                if dc == 0 {
                    PostQuitMessage(1);
                    return 0;
                }
                let result = in_frame(|frame| frame.paint(hwnd, dc));
                let ended = EndPaint(hwnd, &paint);
                if result.is_err() || ended == 0 {
                    PostQuitMessage(1);
                }
            }
            0x0002 => PostQuitMessage(0), // WM_DESTROY
            _ => return DefWindowProcW(hwnd, message, wp, lp),
        }
    }
    0
}

fn create_window() -> io::Result<Handle> {
    let name: Vec<_> = "IFW RW02 native GDI control\0".encode_utf16().collect();
    let title: Vec<_> = "Desktop input probe\0".encode_utf16().collect();
    // The strings and class exist until Windows copies them. The window belongs to this thread.
    unsafe {
        let instance = GetModuleHandleW(ptr::null());
        let class = Class {
            style: 0,
            procedure,
            class_extra: 0,
            window_extra: 0,
            instance,
            icon: 0,
            cursor: 0,
            background: 0,
            menu: ptr::null(),
            name: name.as_ptr(),
        };
        checked(i32::from(RegisterClassW(&class)))?;
        let mut rect = Rect {
            right: WIDTH,
            bottom: HEIGHT,
            ..Default::default()
        };
        checked(AdjustWindowRectEx(&mut rect, STYLE, 0, 0))?;
        let hwnd = CreateWindowExW(
            0,
            name.as_ptr(),
            title.as_ptr(),
            STYLE,
            100,
            90,
            rect.right - rect.left,
            rect.bottom - rect.top,
            0,
            0,
            instance,
            ptr::null_mut(),
        );
        if hwnd == 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(hwnd)
        }
    }
}

fn show(hwnd: Handle) -> io::Result<()> {
    in_frame(Frame::advance)?;
    visibility(hwnd, true)?;
    // Update the owned window's invalidated client synchronously.
    unsafe {
        checked(InvalidateRect(hwnd, ptr::null(), 0))?;
        checked(UpdateWindow(hwnd))
    }
}

fn main() -> io::Result<()> {
    if std::env::var("IFW_QA_BENCHMARK").as_deref() != Ok("1") {
        return Err(io::Error::other(
            "The private hosted worker fixture is required",
        ));
    }
    let mut worker = windows_worker::Benchmark::start()?;
    let token = std::env::var("IFW_QA_INVENTORY_TOKEN").map_err(io::Error::other)?;
    let seed = u32::from_str_radix(
        token
            .get(..6)
            .ok_or_else(|| io::Error::other("Invalid owner token"))?,
        16,
    )
    .map_err(io::Error::other)?;
    let mut command = [0];
    io::stdin().read_exact(&mut command)?;
    if command != *b"T" {
        return Err(io::Error::other("Expected native observer start barrier"));
    }
    worker.release()?;
    let frame = Frame::new(seed)?;
    FRAME.set(Some(frame));
    let hwnd = create_window()?;
    // Thread messages target our existing UI queue, never a recycled HWND.
    let ui_thread = unsafe { GetCurrentThreadId() };
    let commands = thread::spawn(move || -> io::Result<()> {
        let mut input = io::stdin().lock();
        loop {
            let mut byte = [0];
            let next = if input.read_exact(&mut byte).is_ok() {
                byte[0]
            } else {
                0
            };
            checked(unsafe { PostThreadMessageW(ui_thread, CONTROL, usize::from(next), 0) })?;
            if next != b'O' {
                return Ok(());
            }
        }
    });
    show(hwnd)?;
    let mut quit = false;
    let mut message = Message::default();
    loop {
        // GetMessage initializes the mutable MSG and DispatchMessage calls our registered procedure.
        match unsafe { GetMessageW(&mut message, 0, 0, 0) } {
            -1 => return Err(io::Error::last_os_error()),
            0 => break,
            _ if message.window == 0 && message.message == CONTROL => match message.param {
                OPEN => show(hwnd)?,
                QUIT => {
                    quit = true;
                    checked(unsafe { DestroyWindow(hwnd) })?;
                }
                _ => return Err(io::Error::other("Unexpected control byte or input EOF")),
            },
            _ => unsafe {
                TranslateMessage(&message);
                DispatchMessageW(&message);
            },
        }
    }
    if !quit || message.param != 0 {
        return Err(io::Error::other("Unexpected window shutdown"));
    }
    commands
        .join()
        .map_err(|_| io::Error::other("Control reader terminated"))??;
    worker.finish()?;
    let passes = in_frame(|frame| Ok(frame.reported))?;
    FRAME.set(None);
    println!("DRAINED passes={passes}");
    Ok(())
}
