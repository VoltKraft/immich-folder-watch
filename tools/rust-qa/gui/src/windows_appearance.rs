//! Read the user's contrast colors on the thread that owns the root HWND.
use std::cell::Cell;

pub type Rgb = [u8; 3];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Palette {
    pub window: Rgb,
    pub text: Rgb,
    pub highlight: Rgb,
    pub highlight_text: Rgb,
    pub button: Rgb,
    pub button_text: Rgb,
    pub disabled_text: Rgb,
    pub link: Rgb,
}

fn rgb(colorref: u32) -> Rgb {
    let [r, g, b, _] = colorref.to_le_bytes();
    [r, g, b]
}

fn changed_visible(
    previous: &Cell<Option<Palette>>,
    next: Option<Palette>,
    visible: impl FnOnce() -> bool,
) -> bool {
    previous.replace(next) != next && visible()
}

#[cfg(windows)]
pub use native::{attach, current};

#[cfg(windows)]
mod native {
    use super::{Palette, changed_visible, rgb};
    use std::cell::Cell;
    use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
    use windows::Win32::Graphics::Gdi::{
        COLOR_BTNFACE, COLOR_BTNTEXT, COLOR_GRAYTEXT, COLOR_HIGHLIGHT, COLOR_HIGHLIGHTTEXT,
        COLOR_HOTLIGHT, COLOR_WINDOW, COLOR_WINDOWTEXT, GetSysColor, InvalidateRect,
    };
    use windows::Win32::System::Threading::GetCurrentThreadId;
    use windows::Win32::UI::Accessibility::{HCF_HIGHCONTRASTON, HIGHCONTRASTW};
    use windows::Win32::UI::Shell::{DefSubclassProc, RemoveWindowSubclass, SetWindowSubclass};
    use windows::Win32::UI::WindowsAndMessaging::{
        GA_ROOT, GetAncestor, GetWindowThreadProcessId, IsIconic, IsWindowVisible,
        SPI_GETHIGHCONTRAST, SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS, SystemParametersInfoW,
        WM_NCDESTROY, WM_SETTINGCHANGE, WM_SYSCOLORCHANGE, WM_THEMECHANGED,
    };
    use winit::raw_window_handle::{HasWindowHandle, RawWindowHandle};

    // The fixture creates a single root on this thread. No callback borrows an eframe App.
    thread_local! { static PALETTE: Cell<Option<Palette>> = const { Cell::new(None) }; }

    fn read() -> windows::core::Result<Option<Palette>> {
        let mut contrast = HIGHCONTRASTW {
            cbSize: size_of::<HIGHCONTRASTW>() as u32,
            ..Default::default()
        };
        // User32 owns the returned scheme pointer. We only consume the contrast flags.
        unsafe {
            SystemParametersInfoW(
                SPI_GETHIGHCONTRAST,
                contrast.cbSize,
                Some((&raw mut contrast).cast()),
                SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS(0),
            )?;
            Ok(contrast
                .dwFlags
                .contains(HCF_HIGHCONTRASTON)
                .then(|| Palette {
                    window: rgb(GetSysColor(COLOR_WINDOW)),
                    text: rgb(GetSysColor(COLOR_WINDOWTEXT)),
                    highlight: rgb(GetSysColor(COLOR_HIGHLIGHT)),
                    highlight_text: rgb(GetSysColor(COLOR_HIGHLIGHTTEXT)),
                    button: rgb(GetSysColor(COLOR_BTNFACE)),
                    button_text: rgb(GetSysColor(COLOR_BTNTEXT)),
                    disabled_text: rgb(GetSysColor(COLOR_GRAYTEXT)),
                    link: rgb(GetSysColor(COLOR_HOTLIGHT)),
                }))
        }
    }

    unsafe extern "system" fn on_message(
        hwnd: HWND,
        message: u32,
        wparam: WPARAM,
        lparam: LPARAM,
        id: usize,
        _: usize,
    ) -> LRESULT {
        match message {
            WM_SETTINGCHANGE | WM_SYSCOLORCHANGE | WM_THEMECHANGED => {
                if let Ok(next) = read()
                    && PALETTE.with(|value| {
                        changed_visible(value, next, || unsafe {
                            IsWindowVisible(hwnd).as_bool() && !IsIconic(hwnd).as_bool()
                        })
                    })
                {
                    // The resulting WM_PAINT follows winit's ordinary RedrawRequested path.
                    unsafe {
                        let _ = InvalidateRect(Some(hwnd), None, false);
                    }
                }
            }
            WM_NCDESTROY => {
                PALETTE.set(None);
                unsafe {
                    let _ = RemoveWindowSubclass(hwnd, Some(on_message), id);
                }
            }
            _ => {}
        }
        // Preserve other subclasses and the original winit WndProc for every message.
        unsafe { DefSubclassProc(hwnd, message, wparam, lparam) }
    }

    pub fn attach(root: &winit::window::Window) -> Result<(), Box<dyn std::error::Error>> {
        PALETTE.set(None);
        let handle = root.window_handle()?;
        let RawWindowHandle::Win32(raw) = handle.as_raw() else {
            return Err("Expected a Windows root".into());
        };
        let hwnd = HWND(raw.hwnd.get() as _);
        let mut pid = 0;
        // The borrowed HWND belongs to this window. Only install on its creating thread.
        unsafe {
            if GetWindowThreadProcessId(hwnd, Some(&mut pid)) != GetCurrentThreadId()
                || pid != std::process::id()
                || GetAncestor(hwnd, GA_ROOT) != hwnd
            {
                return Err("Contrast observation requires the owned root thread".into());
            }
            if !SetWindowSubclass(hwnd, Some(on_message), 1, 0).as_bool() {
                return Err("Could not install the contrast observer on the root window".into());
            }
        }
        PALETTE.set(read()?);
        Ok(())
    }

    pub fn current() -> Option<Palette> {
        PALETTE.get()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn colorref_preserves_rgb_channel_order() {
        assert_eq!(rgb(0x00d57418), [0x18, 0x74, 0xd5]);
    }

    #[test]
    fn changes_while_hidden_are_available_at_reopen_without_requesting_redraw() {
        let state = Cell::new(None);
        let rgb = [20, 30, 40];
        let first = Palette {
            window: rgb,
            text: rgb,
            highlight: rgb,
            highlight_text: rgb,
            button: rgb,
            button_text: rgb,
            disabled_text: rgb,
            link: rgb,
        };
        let second = Palette {
            disabled_text: [1, 2, 3],
            ..first
        };
        assert!(changed_visible(&state, Some(first), || true));
        assert!(!changed_visible(&state, Some(first), || panic!(
            "No change"
        )));
        assert!(!changed_visible(&state, Some(second), || false));
        assert_eq!(state.get(), Some(second));
        assert!(changed_visible(&state, None, || true));
        assert_eq!(state.get(), None);
    }
}
