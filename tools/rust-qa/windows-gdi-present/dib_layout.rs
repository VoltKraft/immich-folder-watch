//! Layout of a top-down 32-bit DIB backed by a row-aligned wgpu texture copy.
use std::io;

const MAX_EDGE: u32 = 8192;
const MAX_BYTES: u32 = 32 * 1024 * 1024;

#[derive(Clone, Copy, Debug)]
pub(super) struct Layout {
    pub width: u32,
    pub height: u32,
    pub row_bytes: u32,
    pub mapped_bytes: u32,
}

impl Layout {
    pub fn new(width: u32, height: u32, alignment: u32) -> io::Result<Self> {
        if width == 0
            || height == 0
            || width > MAX_EDGE
            || height > MAX_EDGE
            || !alignment.is_power_of_two()
            || !alignment.is_multiple_of(4)
            || alignment > 4096
        {
            return Err(io::Error::other(
                "Unsupported GDI frame dimensions or row alignment",
            ));
        }
        let row_bytes = (width * 4).next_multiple_of(alignment);
        let mapped_bytes = row_bytes * height;
        if mapped_bytes > MAX_BYTES {
            return Err(io::Error::other(
                "GDI readback exceeds the frame byte limit",
            ));
        }
        Ok(Self {
            width,
            height,
            row_bytes,
            mapped_bytes,
        })
    }
}

/// A partial visible DC can legitimately transfer fewer scan lines while another
/// window covers the client. Only an entire transfer may enter the native trace.
#[derive(Clone, Copy)]
pub(super) struct Clip {
    pub kind: i32,
    pub rect: [i32; 4],
}

pub(super) fn complete(
    lines: i32,
    before: Clip,
    after: Clip,
    same_window: bool,
    frame: Layout,
) -> io::Result<bool> {
    let whole = |c: Clip| c.kind == 2 && c.rect == [0, 0, frame.width as i32, frame.height as i32];
    if (0..=frame.height as i32).contains(&lines) {
        if !same_window || !whole(before) || !whole(after) {
            return Ok(false);
        }
        if lines == frame.height as i32 {
            return Ok(true);
        }
    }
    Err(io::Error::other(format!(
        "Incomplete GDI transfer: {lines} scan lines"
    )))
}

#[derive(Clone, Copy)]
pub(super) enum Order {
    Rgba,
    Bgra,
}

impl Order {
    pub fn masks(self) -> [u32; 3] {
        match self {
            Self::Rgba => [0x0000_00ff, 0x0000_ff00, 0x00ff_0000],
            Self::Bgra => [0x00ff_0000, 0x0000_ff00, 0x0000_00ff],
        }
    }

    pub fn rgba(self, value: [u8; 4]) -> [u8; 4] {
        match self {
            Self::Rgba => value,
            Self::Bgra => [value[2], value[1], value[0], value[3]],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn includes_copy_padding_and_preserves_visible_extents() {
        let l = Layout::new(641, 7, 256).unwrap();
        assert_eq!(
            (l.width, l.height, l.row_bytes, l.mapped_bytes),
            (641, 7, 2816, 19712)
        );
        let l = Layout::new(640, 400, 256).unwrap();
        assert_eq!(l.mapped_bytes, 1_024_000);
    }

    #[test]
    fn rejects_invalid_or_excessive_allocations() {
        for (w, h, a) in [
            (0, 4, 256),
            (4, 0, 256),
            (u32::MAX, 2, 256),
            (8192, 1025, 256),
            (2, 2, 0),
            (2, 2, 12),
            (2, 2, 2),
            (2, 2, 8192),
        ] {
            assert!(Layout::new(w, h, a).is_err());
        }
        assert!(Layout::new(8192, 1024, 256).is_ok());
    }

    #[test]
    fn bitmap_and_screenshot_decode_the_same_channel_order() {
        let base = [0x21, 0x4a, 0x8c, 0x90];
        for (order, bytes) in [(Order::Rgba, base), (Order::Bgra, [0x8c, 0x4a, 0x21, 0x90])] {
            let word = u32::from_le_bytes(bytes);
            let channels = order
                .masks()
                .map(|mask| ((word & mask) >> mask.trailing_zeros()) as u8);
            assert_eq!(channels, base[..3]);
            assert_eq!(order.rgba(bytes), base);
        }
    }

    #[test]
    fn a_clipped_transfer_never_counts_as_a_complete_frame() {
        let frame = Layout::new(640, 400, 256).unwrap();
        let whole = Clip {
            kind: 2,
            rect: [0, 0, 640, 400],
        };
        assert!(complete(400, whole, whole, true, frame).unwrap());
        for clipped in [
            Clip {
                kind: 1,
                rect: [0; 4],
            },
            Clip {
                kind: 2,
                rect: [2, 0, 638, 400],
            },
            Clip {
                kind: 3,
                rect: whole.rect,
            },
        ] {
            for lines in [0, 199, 400] {
                assert!(!complete(lines, clipped, whole, true, frame).unwrap());
                assert!(!complete(lines, whole, clipped, true, frame).unwrap());
            }
        }
        assert!(!complete(400, whole, whole, false, frame).unwrap());
        for bad in [-1, 0, 255, 401] {
            assert!(complete(bad, whole, whole, true, frame).is_err());
        }
    }
}
