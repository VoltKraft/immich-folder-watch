//! Portable controls for the state and command code compiled into the retained winit library.
#![allow(non_snake_case)]

use bitflags::bitflags;
use std::cell::RefCell;
use std::sync::{Arc, Mutex, MutexGuard};

type HWND = isize;
const WINDOW: HWND = 37;
const SW_HIDE: i32 = 0;
const SW_SHOW: i32 = 5;
const SW_SHOWNOACTIVATE: i32 = 4;

struct WindowState {
    window_flags: WindowFlags,
    retained_visibility_started: bool,
    skip_taskbar: bool,
    fullscreen: Option<()>,
    dragging: bool,
}

include!("winit_policy.rs");

#[derive(Default)]
struct Native {
    owner: Option<Arc<Mutex<WindowState>>>,
    visible: bool,
    commands: Vec<i32>,
    original_calls: usize,
}

thread_local! {
    static NATIVE: RefCell<Native> = RefCell::default();
}

unsafe fn IsWindowVisible(hwnd: HWND) -> i32 {
    assert_eq!(hwnd, WINDOW);
    NATIVE.with_borrow(|native| i32::from(native.visible))
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
        let previous = native.visible;
        native.visible = visible;
        native.commands.push(command);
        i32::from(previous)
    })
}

impl WindowFlags {
    fn apply_diff(self, hwnd: HWND, new: Self) {
        assert_eq!(hwnd, WINDOW);
        NATIVE.with_borrow_mut(|native| {
            native.original_calls += 1;
            native.visible = new.contains(Self::VISIBLE);
        });
    }
}

fn start(flags: WindowFlags, visible: bool) -> Arc<Mutex<WindowState>> {
    let state = Arc::new(Mutex::new(WindowState {
        window_flags: flags,
        retained_visibility_started: false,
        skip_taskbar: false,
        fullscreen: None,
        dragging: false,
    }));
    NATIVE.with_borrow_mut(|n| {
        *n = Native {
            owner: Some(Arc::clone(&state)),
            visible,
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
        toggle(&state, false);
        toggle(&state, true);
        toggle(&state, true);
        NATIVE.with_borrow(|native| {
            assert_eq!(
                native.commands,
                [SW_HIDE, if active { SW_SHOW } else { SW_SHOWNOACTIVATE }]
            );
            assert_eq!(native.original_calls, 2); // Initial show and duplicate request.
            assert!(native.visible);
        });
    }
}

#[test]
fn a_native_hidden_root_cannot_arm_the_fast_path() {
    let state = start(ordinary() | WindowFlags::VISIBLE, false);
    toggle(&state, false);
    toggle(&state, true);
    assert!(!state.lock().unwrap().retained_visibility_started);
    NATIVE.with_borrow(|n| assert_eq!((n.commands.len(), n.original_calls), (0, 2)));
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
        NATIVE.with_borrow(|n| assert_eq!(n.original_calls, 1));
    }
    for flags in [
        ordinary - WindowFlags::ON_TASKBAR,
        ordinary - WindowFlags::MARKER_DECORATIONS,
    ] {
        let state = start(flags, true);
        toggle(&state, false);
        NATIVE.with_borrow(|n| assert_eq!(n.original_calls, 1));
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
        NATIVE.with_borrow(|n| assert_eq!((n.commands.len(), n.original_calls), (0, 1)));
    }
}
