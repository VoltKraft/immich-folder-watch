//! Windows SDK ABI used by the two native 64-bit targets.
use std::ffi::c_void;

pub type Handle = isize;
pub type Proc = extern "system" fn(Handle, u32, usize, isize) -> isize;

#[repr(C)]
#[derive(Default)]
pub struct Point {
    pub x: i32,
    pub y: i32,
}

#[repr(C)]
#[derive(Default)]
pub struct Rect {
    pub left: i32,
    pub top: i32,
    pub right: i32,
    pub bottom: i32,
}

#[repr(C)]
#[derive(Default)]
pub struct Message {
    pub window: Handle,
    pub message: u32,
    pub param: usize,
    long_param: isize,
    time: u32,
    point: Point,
    private: u32,
}

#[repr(C)]
pub struct Class {
    pub style: u32,
    pub procedure: Proc,
    pub class_extra: i32,
    pub window_extra: i32,
    pub instance: Handle,
    pub icon: Handle,
    pub cursor: Handle,
    pub background: Handle,
    pub menu: *const u16,
    pub name: *const u16,
}

#[repr(C)]
#[derive(Default)]
pub struct Paint {
    dc: Handle,
    erase: i32,
    bounds: Rect,
    restore: i32,
    update: i32,
    reserved: [u8; 32],
}

#[repr(C)]
#[derive(Default)]
pub struct BitmapHeader {
    pub size: u32,
    pub width: i32,
    pub height: i32,
    pub planes: u16,
    pub bits: u16,
    compression: u32,
    image_size: u32,
    horizontal_resolution: i32,
    vertical_resolution: i32,
    colors: u32,
    important_colors: u32,
}

#[repr(C)]
#[derive(Default)]
pub struct BitmapInfo {
    pub header: BitmapHeader,
    color: u32,
}

const _: () = {
    assert!(size_of::<Class>() == 72);
    assert!(size_of::<Message>() == 48);
    assert!(size_of::<Paint>() == 72);
    assert!(size_of::<BitmapHeader>() == 40);
};

#[link(name = "kernel32")]
unsafe extern "system" {
    pub fn GetModuleHandleW(module: *const u16) -> Handle;
    pub fn GetCurrentThreadId() -> u32;
    pub fn QueryPerformanceCounter(value: *mut i64) -> i32;
}

#[link(name = "user32")]
unsafe extern "system" {
    pub fn RegisterClassW(class: *const Class) -> u16;
    pub fn AdjustWindowRectEx(bounds: *mut Rect, style: u32, has_menu: i32, extended: u32) -> i32;
    pub fn CreateWindowExW(
        extended: u32,
        class: *const u16,
        title: *const u16,
        style: u32,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
        parent: Handle,
        menu: Handle,
        instance: Handle,
        data: *mut c_void,
    ) -> Handle;
    pub fn DefWindowProcW(hwnd: Handle, message: u32, wparam: usize, lparam: isize) -> isize;
    pub fn DestroyWindow(hwnd: Handle) -> i32;
    pub fn IsWindowVisible(hwnd: Handle) -> i32;
    pub fn ShowWindow(hwnd: Handle, command: i32) -> i32;
    pub fn GetClientRect(hwnd: Handle, bounds: *mut Rect) -> i32;
    pub fn InvalidateRect(hwnd: Handle, bounds: *const Rect, erase: i32) -> i32;
    pub fn UpdateWindow(hwnd: Handle) -> i32;
    pub fn BeginPaint(hwnd: Handle, paint: *mut Paint) -> Handle;
    pub fn EndPaint(hwnd: Handle, paint: *const Paint) -> i32;
    pub fn GetMessageW(message: *mut Message, hwnd: Handle, min: u32, max: u32) -> i32;
    pub fn TranslateMessage(message: *const Message) -> i32;
    pub fn DispatchMessageW(message: *const Message) -> isize;
    pub fn PostThreadMessageW(thread: u32, message: u32, wparam: usize, lparam: isize) -> i32;
    pub fn PostQuitMessage(code: i32);
}

#[link(name = "gdi32")]
unsafe extern "system" {
    pub fn CreateCompatibleDC(dc: Handle) -> Handle;
    pub fn CreateDIBSection(
        dc: Handle,
        info: *const BitmapInfo,
        usage: u32,
        bits: *mut *mut c_void,
        section: Handle,
        offset: u32,
    ) -> Handle;
    pub fn SelectObject(dc: Handle, object: Handle) -> Handle;
    pub fn BitBlt(
        dest: Handle,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
        source: Handle,
        source_x: i32,
        source_y: i32,
        raster: u32,
    ) -> i32;
    pub fn GdiFlush() -> i32;
    pub fn DeleteDC(dc: Handle) -> i32;
    pub fn DeleteObject(object: Handle) -> i32;
}
