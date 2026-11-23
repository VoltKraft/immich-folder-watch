//! Portable controls for the state and command code compiled into the retained winit library.
#![allow(non_snake_case)]

use bitflags::bitflags;
use std::cell::RefCell;
use std::sync::{Arc, Mutex, MutexGuard};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    GWL_EXSTYLE, GWL_STYLE, SW_HIDE, SW_SHOW, SW_SHOWNOACTIVATE, WINDOW_EX_STYLE, WINDOW_STYLE,
    WS_BORDER, WS_CAPTION, WS_CHILD, WS_CLIPCHILDREN, WS_CLIPSIBLINGS, WS_DISABLED,
    WS_EX_ACCEPTFILES, WS_EX_APPWINDOW, WS_EX_LAYERED, WS_EX_NOREDIRECTIONBITMAP, WS_EX_TOPMOST,
    WS_EX_TRANSPARENT, WS_EX_WINDOWEDGE, WS_MAXIMIZE, WS_MAXIMIZEBOX, WS_MINIMIZE, WS_MINIMIZEBOX,
    WS_OVERLAPPEDWINDOW, WS_POPUP, WS_SIZEBOX, WS_SYSMENU, WS_VISIBLE,
};

type HWND = isize;
const WINDOW: HWND = 37;

struct WindowState {
    window_flags: WindowFlags,
    retained_visibility_started: bool,
    trace_retained_visibility: bool,
    skip_taskbar: bool,
    fullscreen: Option<()>,
    dragging: bool,
}

// Capture the exact launcher line only after its native command has returned.
macro_rules! eprintln {
    ($($arg:tt)*) => {
        NATIVE.with_borrow_mut(|n| {
            let message = format!($($arg)*);
            let command = n.commands.last().expect("marker must follow ShowWindow");
            let action = if *command == SW_HIDE { "hide" } else { "show" };
            assert_eq!(message, format!("RETAINED_VISIBILITY first={action} hwnd={WINDOW}"));
            n.markers.push(message);
        })
    };
}

include!("winit_policy.rs");

#[derive(Default)]
struct Native {
    owner: Option<Arc<Mutex<WindowState>>>,
    style: WINDOW_STYLE,
    style_ex: WINDOW_EX_STYLE,
    reads: Vec<i32>,
    commands: Vec<i32>,
    markers: Vec<String>,
    original_calls: usize,
}

thread_local! {
    static NATIVE: RefCell<Native> = RefCell::default();
}

unsafe fn GetWindowLongW(hwnd: HWND, field: i32) -> i32 {
    assert_eq!(hwnd, WINDOW);
    NATIVE.with_borrow_mut(|native| {
        native.reads.push(field);
        match field {
            GWL_STYLE => native.style as i32,
            GWL_EXSTYLE => native.style_ex as i32,
            _ => panic!("unexpected native state query"),
        }
    })
}

unsafe fn ShowWindow(hwnd: HWND, command: i32) -> i32 {
    assert_eq!(hwnd, WINDOW);
    NATIVE.with_borrow_mut(|native| {
        let visible = command != SW_HIDE;
        let state = native
            .owner
            .as_ref()
            .unwrap()
            .try_lock()
            .expect("reentrant window message");
        assert_eq!(state.window_flags.contains(WindowFlags::VISIBLE), visible);
        let previous = native.style & WS_VISIBLE != 0;
        if visible {
            native.style |= WS_VISIBLE;
        } else {
            native.style &= !WS_VISIBLE;
        }
        native.commands.push(command);
        i32::from(previous)
    })
}

impl WindowFlags {
    fn apply_diff(self, hwnd: HWND, new: Self) {
        assert_eq!(hwnd, WINDOW);
        NATIVE.with_borrow_mut(|native| {
            native.original_calls += 1;
            (native.style, native.style_ex) = new.to_window_styles();
        });
    }
}

fn start(flags: WindowFlags, visible: bool) -> Arc<Mutex<WindowState>> {
    let state = Arc::new(Mutex::new(WindowState {
        window_flags: flags,
        retained_visibility_started: false,
        trace_retained_visibility: false,
        skip_taskbar: false,
        fullscreen: None,
        dragging: false,
    }));
    NATIVE.with_borrow_mut(|n| {
        let (style, style_ex) = (flags - WindowFlags::VISIBLE).to_window_styles();
        *n = Native {
            owner: Some(Arc::clone(&state)),
            style: if visible { style | WS_VISIBLE } else { style },
            style_ex,
            ..Native::default()
        }
    });
    state
}

fn toggle(state: &Mutex<WindowState>, show: bool) {
    WindowState::set_window_flags(state.lock().unwrap(), WINDOW, |f| {
        f.set(WindowFlags::VISIBLE, show)
    });
}

fn ordinary() -> WindowFlags {
    WindowFlags::ON_TASKBAR
        | WindowFlags::MARKER_DECORATIONS
        | WindowFlags::RESIZABLE
        | WindowFlags::CLOSABLE
}

#[test]
fn initial_placement_uses_original_then_ordinary_cycles_preserve_state_and_activation() {
    for active in [false, true] {
        let mut flags = ordinary();
        flags.set(WindowFlags::MARKER_ACTIVATE, active);
        let state = start(flags, false);
        toggle(&state, true);
        NATIVE.with_borrow(|n| assert!(n.reads.is_empty())); // Preserve initial placement.
        toggle(&state, false);
        toggle(&state, true);
        toggle(&state, true);
        NATIVE.with_borrow(|native| {
            assert_eq!(
                native.commands,
                [SW_HIDE, if active { SW_SHOW } else { SW_SHOWNOACTIVATE }]
            );
            assert_eq!(native.original_calls, 2); // Initial show and duplicate request.
            assert_eq!(
                native.reads,
                [GWL_STYLE, GWL_EXSTYLE, GWL_STYLE, GWL_EXSTYLE]
            );
            assert_ne!(native.style & WS_VISIBLE, 0);
            assert!(native.markers.is_empty());
        });
    }
}

#[test]
fn external_native_changes_use_the_original_path_before_and_after_arming() {
    // Exercise a first hide, an armed show, and an armed hide on the same real flag transitions.
    for history in [&[][..], &[false], &[false, true]] {
        let changes: &[(&str, fn(&mut Native))] = &[
            ("visibility mismatch", |n| n.style ^= WS_VISIBLE),
            ("system minimize", |n| n.style |= WS_MINIMIZE),
            ("system maximize", |n| n.style |= WS_MAXIMIZE),
            ("child", |n| n.style |= WS_CHILD),
            ("popup", |n| n.style |= WS_POPUP),
            ("disabled", |n| n.style |= WS_DISABLED),
            ("removed caption", |n| n.style &= !WS_CAPTION),
            ("removed taskbar style", |n| n.style_ex &= !WS_EX_APPWINDOW),
            ("topmost", |n| n.style_ex |= WS_EX_TOPMOST),
            ("style query failed", |n| n.style = 0),
            ("extended style query failed", |n| n.style_ex = 0),
        ];
        for &(name, change) in changes {
            let state = start(ordinary() | WindowFlags::VISIBLE, true);
            for &show in history {
                toggle(&state, show);
            }
            let was_visible = state
                .lock()
                .unwrap()
                .window_flags
                .contains(WindowFlags::VISIBLE);
            NATIVE.with_borrow_mut(change);
            toggle(&state, !was_visible);
            let locked = state.lock().unwrap();
            assert_eq!(
                locked.retained_visibility_started,
                !history.is_empty(),
                "{name}"
            );
            assert_eq!(
                locked.window_flags.contains(WindowFlags::VISIBLE),
                !was_visible,
                "{name}"
            );
            NATIVE.with_borrow(|n| {
                assert_eq!(
                    (n.commands.len(), n.original_calls),
                    (history.len(), 1),
                    "{name}"
                );
            });
        }
    }
}

#[test]
fn launcher_marks_both_actual_native_commands_once_even_after_a_fallback() {
    let state = start(ordinary() | WindowFlags::VISIBLE, true);
    state.lock().unwrap().trace_retained_visibility = true;
    toggle(&state, false);
    NATIVE.with_borrow_mut(|n| n.style |= WS_MAXIMIZE);
    toggle(&state, true);
    NATIVE.with_borrow(|n| {
        assert_eq!(n.original_calls, 1);
        assert_eq!(
            n.markers,
            [format!("RETAINED_VISIBILITY first=hide hwnd={WINDOW}")]
        );
    });
    for show in [false, true, false, true] {
        toggle(&state, show);
    }
    NATIVE.with_borrow(|n| {
        assert_eq!(
            n.commands,
            [
                SW_HIDE,
                SW_HIDE,
                SW_SHOWNOACTIVATE,
                SW_HIDE,
                SW_SHOWNOACTIVATE
            ]
        );
        assert_eq!(
            n.markers,
            [
                format!("RETAINED_VISIBILITY first=hide hwnd={WINDOW}"),
                format!("RETAINED_VISIBILITY first=show hwnd={WINDOW}")
            ]
        );
    });
}

#[test]
fn unusual_and_combined_changes_stay_on_the_original_path() {
    let ordinary = ordinary() | WindowFlags::VISIBLE;
    for flag in [
        WindowFlags::CHILD,
        WindowFlags::POPUP,
        WindowFlags::MINIMIZED,
        WindowFlags::MAXIMIZED,
        WindowFlags::MARKER_BORDERLESS_FULLSCREEN,
        WindowFlags::MARKER_EXCLUSIVE_FULLSCREEN,
        WindowFlags::ALWAYS_ON_TOP,
        WindowFlags::ALWAYS_ON_BOTTOM,
        WindowFlags::TRANSPARENT,
        WindowFlags::NO_BACK_BUFFER,
        WindowFlags::MARKER_IN_SIZE_MOVE,
        WindowFlags::IGNORE_CURSOR_EVENT,
        WindowFlags::MARKER_RETAIN_STATE_ON_SIZE,
        WindowFlags::from_bits_retain(1 << 30),
    ] {
        let state = start(ordinary | flag, true);
        toggle(&state, false);
        NATIVE.with_borrow(|n| assert_eq!((n.original_calls, n.reads.len()), (1, 0)));
    }
    for flags in [
        ordinary - WindowFlags::ON_TASKBAR,
        ordinary - WindowFlags::MARKER_DECORATIONS,
    ] {
        let state = start(flags, true);
        toggle(&state, false);
        NATIVE.with_borrow(|n| assert_eq!((n.original_calls, n.reads.len()), (1, 0)));
    }
    for condition in 0..4 {
        let state = start(ordinary, true);
        let mut locked = state.lock().unwrap();
        locked.skip_taskbar = condition == 0;
        locked.fullscreen = (condition == 1).then_some(());
        locked.dragging = condition == 2;
        WindowState::set_window_flags(locked, WINDOW, |f| {
            f.remove(WindowFlags::VISIBLE);
            if condition == 3 {
                f.remove(WindowFlags::CLOSABLE);
            }
        });
        NATIVE.with_borrow(|n| {
            assert_eq!(
                (n.commands.len(), n.original_calls, n.reads.len()),
                (0, 1, 0)
            )
        });
    }
}
