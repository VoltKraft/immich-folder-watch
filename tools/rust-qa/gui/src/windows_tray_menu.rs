//! Display the elected receiver's native notification-area menu on its own thread.
use crate::windows_tray_shell::{ICON, Icon};
use crate::windows_tray_state::TrayAction;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use windows::Win32::Foundation::{HWND, LPARAM, POINT, WPARAM};
use windows::Win32::UI::Shell::NIM_SETFOCUS;
use windows::Win32::UI::WindowsAndMessaging::*;
use windows::core::{HSTRING, Owned, PCWSTR, Result};

#[derive(Clone)]
pub struct TrayLanguage(Arc<AtomicBool>);

impl TrayLanguage {
    pub(crate) fn german() -> Self {
        Self(Arc::new(AtomicBool::new(true)))
    }

    pub fn set_german(&self, german: bool) {
        self.0.store(german, Ordering::Release);
    }
}

#[derive(Default)]
pub(crate) struct MenuControl {
    pub(crate) stopping: AtomicBool,
    // Published only while the live receiver thread tracks this popup.
    active_owner: Mutex<Option<usize>>,
}

impl MenuControl {
    pub(crate) fn cancel_popup(&self) {
        let owner = self.active_owner.lock().expect("tray menu owner");
        if let Some(hwnd) = *owner {
            // DefWindowProc cancels its active menu. The receiver cannot retire
            // its HWND until the tracking call returns and this lock is released.
            unsafe {
                let _ = PostMessageW(Some(HWND(hwnd as _)), WM_CANCELMODE, WPARAM(0), LPARAM(0));
            }
        }
    }

    pub(crate) fn select(
        &self,
        icon: &Icon<'_>,
        language: &TrayLanguage,
    ) -> Result<Option<TrayAction>> {
        let hwnd = icon.owner.hwnd;
        let german = language.0.load(Ordering::Acquire);
        // The version 4 WM_CONTEXTMENU callback supplies no documented point.
        // Anchor keyboard activation to this icon when the pointer is elsewhere.
        let mut pointer = POINT::default();
        let cursor = unsafe { GetCursorPos(&mut pointer) }.map(|()| (pointer.x, pointer.y));
        let (x, y) = match icon.rect() {
            Ok(rect) if rect.right > rect.left && rect.bottom > rect.top => match cursor {
                Ok((x, y))
                    if (rect.left..rect.right).contains(&x)
                        && (rect.top..rect.bottom).contains(&y) =>
                {
                    (x, y)
                }
                _ => (
                    rect.left.midpoint(rect.right),
                    rect.top.midpoint(rect.bottom),
                ),
            },
            _ => cursor?,
        };
        // CreatePopupMenu transfers one newly allocated HMENU. Owned destroys
        // it on every exit, after Windows finishes its modal tracking loop.
        let menu = unsafe { Owned::new(CreatePopupMenu()?) };
        for action in TrayAction::ITEMS {
            unsafe {
                if action != TrayAction::Open {
                    AppendMenuW(*menu, MF_SEPARATOR, 0, PCWSTR::null())?;
                }
                AppendMenuW(
                    *menu,
                    MF_STRING,
                    action as usize,
                    &HSTRING::from(action.label(german)),
                )?;
            }
        }
        // Shell supplied the user gesture. Foreground ownership lets the menu
        // dismiss on an outside click, including when the editor is hidden.
        if !unsafe { SetForegroundWindow(hwnd) }.as_bool()
            && unsafe { GetForegroundWindow() } != hwnd
        {
            eprintln!("Windows declined foreground ownership for the tray menu");
        }
        {
            let mut owner = self.active_owner.lock().expect("tray menu owner");
            if self.stopping.load(Ordering::Acquire) {
                return Ok(None);
            }
            *owner = Some(hwnd.0 as usize);
        }
        println!(
            "TRAY_MENU_OPENED pid={} hwnd={} id={ICON} x={x} y={y} language={}",
            std::process::id(),
            hwnd.0 as usize,
            if german { "de" } else { "en" }
        );
        let flags =
            TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON | TPM_RIGHTALIGN | TPM_BOTTOMALIGN;
        let command = unsafe { TrackPopupMenuEx(*menu, flags.0, x, y, hwnd, None) };
        *self.active_owner.lock().expect("tray menu owner") = None;
        // Microsoft's documented follow-up permits opening the tray menu twice.
        if let Err(error) = unsafe { PostMessageW(Some(hwnd), WM_NULL, WPARAM(0), LPARAM(0)) } {
            eprintln!("Windows tray menu follow-up unavailable: {error}");
        }
        let action = TrayAction::ITEMS
            .into_iter()
            .find(|action| *action as i32 == command.0);
        if let Some(action) = action {
            println!(
                "TRAY_MENU_SELECTED pid={} hwnd={} id={ICON} action={}",
                std::process::id(),
                hwnd.0 as usize,
                action.name()
            );
        }
        if action != Some(TrayAction::Open) {
            icon.call("menu.focus", NIM_SETFOCUS, &icon.base());
        }
        Ok(action)
    }
}
