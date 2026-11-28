//! Native producer control. Draw only into a private top-down DIB and preserve its original BGRA words.
//! The small size comes from SM_CXSMICON and SM_CYSMICON on the test host. DrawIconEx uses
//! the same non-shared HICON that the GUI producer supplies to the Shell. The resulting
//! pixels measure the handle and Win32 scaling independently of notification-area placement.
//! [DrawIconEx](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-drawiconex)
//! and [CreateDIBSection](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-createdibsection).

use std::fmt::Write;
use std::mem::ManuallyDrop;
use windows::Win32::Graphics::Gdi::{
    BI_RGB, BITMAPINFO, BITMAPINFOHEADER, CreateCompatibleDC, CreateDIBSection, DIB_RGB_COLORS,
    DeleteDC, DeleteObject, GdiFlush, GetCurrentObject, OBJ_BITMAP, SelectObject,
};
use windows::Win32::UI::WindowsAndMessaging::{
    DI_NORMAL, DestroyIcon, DrawIconEx, GetSystemMetrics, HICON, SM_CXSMICON, SM_CYSMICON,
};

use super::shell::image;

fn capture(icon: HICON, width: i32, height: i32, background: u32) -> Result<Vec<u32>, String> {
    let info = BITMAPINFO {
        bmiHeader: BITMAPINFOHEADER {
            biSize: size_of::<BITMAPINFOHEADER>() as u32,
            biWidth: width,
            biHeight: -height,
            biPlanes: 1,
            biBitCount: 32,
            biCompression: BI_RGB.0,
            ..Default::default()
        },
        ..Default::default()
    };
    // This memory DC starts with its own stock bitmap. It never selects a window or screen DC.
    let dc = unsafe { CreateCompatibleDC(None) };
    if dc.is_invalid() {
        return Err("CreateCompatibleDC failed".into());
    }
    let mut bits = std::ptr::null_mut();
    let bitmap = unsafe { CreateDIBSection(Some(dc), &info, DIB_RGB_COLORS, &mut bits, None, 0) };
    let bitmap = match bitmap {
        Ok(bitmap) => bitmap,
        Err(err) => {
            let dc_deleted = unsafe { DeleteDC(dc).as_bool() };
            return Err(format!(
                "CreateDIBSection failed: {err}; DeleteDC={dc_deleted}"
            ));
        }
    };
    let previous = unsafe { SelectObject(dc, bitmap.into()) };
    let result = (|| {
        if previous.is_invalid()
            || bits.is_null()
            || !bits.cast::<u32>().is_aligned()
            || unsafe { GetCurrentObject(dc, OBJ_BITMAP) } != bitmap.into()
        {
            return Err("The owned DIB was not selected or its pixels were unavailable".into());
        }
        let count = (width * height) as usize;
        // Caller bounds both dimensions. Each aligned top-down scan line is exactly width * 4 bytes.
        unsafe { std::slice::from_raw_parts_mut(bits.cast::<u32>(), count) }.fill(background);
        let draw = unsafe { DrawIconEx(dc, 0, 0, icon, width, height, 0, None, DI_NORMAL) };
        let flushed = unsafe { GdiFlush().as_bool() };
        if draw.is_err() || !flushed || unsafe { GetCurrentObject(dc, OBJ_BITMAP) } != bitmap.into()
        {
            return Err(format!(
                "DrawIconEx={draw:?}; GdiFlush={flushed}; could not confirm the rendered DIB"
            ));
        }
        // Copy after this thread's GDI batch completed and before releasing the selected bitmap.
        Ok(unsafe { std::slice::from_raw_parts(bits.cast::<u32>(), count) }.to_vec())
    })();
    let restored = previous.is_invalid()
        || unsafe {
            SelectObject(dc, previous) == bitmap.into()
                && GetCurrentObject(dc, OBJ_BITMAP) == previous
        };
    // Deleting the private DC first also deselects the bitmap if restoration failed.
    let dc_deleted = unsafe { DeleteDC(dc).as_bool() };
    let dib_deleted = (restored || dc_deleted) && unsafe { DeleteObject(bitmap.into()).as_bool() };
    if !restored || !dc_deleted || !dib_deleted {
        return Err(format!(
            "DIB cleanup failed: restored={restored} dcDeleted={dc_deleted} dibDeleted={dib_deleted}"
        ));
    }
    result
}

#[test]
fn archived_marker_pixels_survive_native_hicon_rasterization() -> Result<(), String> {
    let small = unsafe { (GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON)) };
    if !(8..=128).contains(&small.0) || !(8..=128).contains(&small.1) {
        return Err(format!("Unexpected native small icon metrics: {small:?}"));
    }
    let mut incorrect = 0;
    // Canonical x64 tray challenges from Actions archives 14973991781 and 14981286389.
    for rgb in [[0x1f, 0xc6, 0x53], [0x33, 0xc7, 0x33]] {
        let marker = u32::from_be_bytes([0, rgb[0], rgb[1], rgb[2]]);
        let icon = image(rgb).map_err(|e| format!("The shared tray producer failed: {e}"))?;
        let observed = (|| {
            for (scale, (width, height)) in [("source", (32, 32)), ("systemSmall", small)] {
                // The full unscaled 22x22 marker is opaque. At a scaled size sample its
                // central half, leaving a margin for edge interpolation by DrawIconEx.
                let (left, top, right, bottom) = if scale == "source" {
                    (5, 5, 27, 27)
                } else {
                    (
                        (width + 3) / 4,
                        (height + 3) / 4,
                        width * 3 / 4,
                        height * 3 / 4,
                    )
                };
                for background in [0xff00_0000, 0xffff_ffff] {
                    let pixels = capture(icon.0, width, height, background)?;
                    let mut words = String::with_capacity(pixels.len() * 8);
                    for word in &pixels {
                        write!(words, "{word:08x}").expect("writing to a String");
                    }
                    let mut exact = 0;
                    for y in top..bottom {
                        for x in left..right {
                            if (pixels[(y * width + x) as usize] & 0xff_ffff) == marker {
                                exact += 1;
                            }
                        }
                    }
                    let total = (right - left) * (bottom - top);
                    println!(
                        "HICON_RASTER rgb={marker:06x} scale={scale} width={width} height={height} background={background:08x} interior={left},{top},{right},{bottom} exact={exact}/{total} pixels={words}"
                    );
                    incorrect += total - exact;
                }
            }
            Ok::<(), String>(())
        })();
        // Transfer the producer's owned handle for checked destruction exactly once.
        let icon = ManuallyDrop::new(icon);
        unsafe { DestroyIcon(icon.0) }.map_err(|e| format!("DestroyIcon failed: {e}"))?;
        println!("HICON_RELEASED rgb={marker:06x}");
        observed?;
    }
    if incorrect != 0 {
        return Err(format!(
            "{incorrect} interior pixels differed from their opaque marker"
        ));
    }
    Ok(())
}
