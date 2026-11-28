//! Own the elected GUI's notification icon independently of its eframe window generations.
use crate::windows_tray_menu::{MenuControl, TrayLanguage};
use crate::windows_tray_shell::{EVENTS, ICON, Icon, Image, Receiver, color, image, pump_messages};
use crate::windows_tray_state::{Attempt, BoundHost, Host, Pending, Recovery, TrayEvent};
use std::io;
use std::sync::Arc;
use std::sync::atomic::Ordering;
use std::sync::mpsc::{Receiver as Channel, SyncSender, TrySendError, sync_channel};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use windows::Win32::Foundation::{HANDLE, WAIT_OBJECT_0, WAIT_TIMEOUT};
use windows::Win32::System::Threading::{OpenProcess, PROCESS_SYNCHRONIZE, WaitForSingleObject};
use windows::Win32::UI::Shell::*;
use windows::Win32::UI::WindowsAndMessaging::*;
use windows::core::{Owned, w};

#[derive(Clone, Copy)]
pub enum TrayRequest {
    ChangeMarker,
    Sample,
}

pub struct NativeTray {
    pub requests: SyncSender<TrayRequest>,
    pub language: TrayLanguage,
    menu: Arc<MenuControl>,
    thread: Option<JoinHandle<io::Result<()>>>,
}

impl NativeTray {
    /// The caller must already hold the launcher's elected primary and the worker's pinned synthetic profile.
    pub fn start<T>(
        token: String,
        deliver: impl Fn(TrayEvent) -> Result<(), TrySendError<T>> + Send + 'static,
    ) -> io::Result<(Self, bool)> {
        if token.len() != 32 || !token.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(io::Error::other("Expected a marked native tray profile"));
        }
        let (requests, input) = sync_channel(8);
        let (ready, outcome) = sync_channel(1);
        let menu = Arc::new(MenuControl::default());
        let owner = Arc::clone(&menu);
        let language = TrayLanguage::german();
        let thread_language = language.clone();
        let thread = thread::Builder::new()
            .name("native-tray".into())
            .spawn(move || run(&token, &owner, &thread_language, input, ready, deliver))?;
        let mut tray = Self {
            requests,
            menu,
            language,
            thread: Some(thread),
        };
        match outcome.recv() {
            Ok(available) => Ok((tray, available)),
            Err(_) => {
                tray.stop()?;
                Err(io::Error::other(
                    "Tray receiver exited before reporting registration",
                ))
            }
        }
    }

    pub fn stop(&mut self) -> io::Result<()> {
        self.menu.stopping.store(true, Ordering::Release);
        if let Some(thread) = self.thread.take() {
            // TrackPopupMenuEx owns a nested OS loop. Permit shutdown even
            // while a user leaves a menu open and all input pipes stay open.
            while !thread.is_finished() {
                self.menu.cancel_popup();
                std::thread::sleep(Duration::from_millis(20));
            }
            thread
                .join()
                .map_err(|_| io::Error::other("Tray thread panicked"))??;
        }
        Ok(())
    }
}

impl Drop for NativeTray {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

fn taskbar() -> Option<Host> {
    // Observe only the notification host on the receiver's desktop.
    unsafe {
        let bar = FindWindowW(w!("Shell_TrayWnd"), None).ok()?;
        let mut pid = 0;
        GetWindowThreadProcessId(bar, Some(&mut pid));
        (pid != 0).then_some((bar.0 as usize, pid))
    }
}

fn shell_host() -> Option<Host> {
    let host = taskbar()?;
    // Corroborate the taskbar window class with the desktop Shell process reported by Windows.
    let window = unsafe { GetShellWindow() };
    let mut pid = 0;
    if window.is_invalid() || unsafe { GetWindowThreadProcessId(window, Some(&mut pid)) } == 0 {
        return None;
    }
    (host.1 == pid).then_some(host)
}

fn pin_shell() -> Option<(Host, Owned<HANDLE>)> {
    let host = shell_host()?;
    // Take ownership of a non-inheritable handle with only the right to wait on this process.
    let process = unsafe { Owned::new(OpenProcess(PROCESS_SYNCHRONIZE, false, host.1).ok()?) };
    (unsafe { WaitForSingleObject(*process, 0) } == WAIT_TIMEOUT && shell_host() == Some(host))
        .then_some((host, process))
}

struct Registration<'a> {
    icon: Icon<'a>,
    images: [Image; 2],
    colors: [[u8; 3]; 2],
    selected: usize,
    available: bool,
    host: BoundHost<Owned<HANDLE>>,
}

impl Registration<'_> {
    fn bind(&mut self, phase: &str, candidate: Option<(Host, Owned<HANDLE>)>) {
        let owner = self.host.confirm(candidate, shell_host(), |handle| {
            (unsafe { WaitForSingleObject(**handle, 0) }) == WAIT_TIMEOUT
        });
        let (hwnd, pid) = owner.unwrap_or_default();
        println!(
            "TRAY_BIND phase={phase} pid={} hwnd={} id={ICON} shell_pid={pid} shell_hwnd={hwnd} verified={}",
            std::process::id(),
            self.icon.owner.hwnd.0 as usize,
            u8::from(owner.is_some())
        );
    }

    fn register(&mut self, phase: &str, token: &str) -> io::Result<bool> {
        let candidate = pin_shell();
        let (added, v4) = self.icon.register(phase, self.images[self.selected].0);
        if added {
            self.bind(phase, candidate);
        }
        println!(
            "TRAY_REGISTER phase={phase} pid={} hwnd={} id={ICON} token={token} added={} version4={}",
            std::process::id(),
            self.icon.owner.hwnd.0 as usize,
            u8::from(added),
            u8::from(v4)
        );
        self.available = added && v4;
        if added && !v4 {
            if !self.icon.remove("incompatible_version") {
                return Err(io::Error::other("Failed to withdraw the rejected v4 icon"));
            }
            self.host.clear();
        }
        Ok(self.available)
    }

    fn recover(&mut self, attempt: Attempt, token: &str) -> io::Result<bool> {
        let phase = match attempt {
            Attempt::Recreate => "recreate",
            Attempt::Retry => "retry",
        };
        // A broadcast can also mean a DPI change. A surviving entry still needs a v4
        // acknowledgement on this host. A duplicate NIM_ADD alone would be refused.
        if self.icon.cleanup {
            let candidate = pin_shell();
            let mut version = self.icon.base();
            version.Anonymous.uVersion = NOTIFYICON_VERSION_4;
            if self
                .icon
                .call("existing.version4", NIM_SETVERSION, &version)
            {
                self.bind(phase, candidate);
                self.available = true;
                return Ok(true);
            }
            // Only this receiver's HWND/ID is withdrawn before retrying a fresh add.
            if self
                .icon
                .rect()
                .is_ok_and(|r| r.right > r.left && r.bottom > r.top)
            {
                // A responsive Shell has this key but did not acknowledge its version.
                // This entry can no longer be attributed to any previous bound process.
                self.host.clear();
                if !self.icon.remove("existing.withdraw") {
                    self.available = false;
                    return Ok(false);
                }
            }
        }
        self.register(phase, token)
    }

    fn retire_exited_host(&mut self) -> bool {
        let absent = || unsafe {
            FindWindowW(w!("Shell_TrayWnd"), None).is_err() && GetShellWindow().is_invalid()
        };
        let Some((hwnd, pid)) = self.host.departed(
            |handle| unsafe { WaitForSingleObject(**handle, 0) } == WAIT_OBJECT_0,
            || absent() && self.icon.rect().is_err() && absent(),
        ) else {
            return false;
        };
        println!(
            "TRAY_RETIRED pid={} hwnd={} id={ICON} shell_pid={pid} shell_hwnd={hwnd}",
            std::process::id(),
            self.icon.owner.hwnd.0 as usize
        );
        self.icon.cleanup = false;
        true
    }

    fn sample(&self, phase: &str, ok: bool) {
        let rect = self
            .icon
            .rect()
            .ok()
            .filter(|r| r.right > r.left && r.bottom > r.top)
            .map_or_else(
                || "none".to_owned(),
                |r| format!("{},{},{},{}", r.left, r.top, r.right, r.bottom),
            );
        let [r, g, b] = self.colors[self.selected];
        println!(
            "TRAY_ICON phase={phase} pid={} hwnd={} id={ICON} rgb={r:02x}{g:02x}{b:02x} rect={rect} ok={}",
            std::process::id(),
            self.icon.owner.hwnd.0 as usize,
            u8::from(ok)
        );
    }

    fn change(&mut self) {
        if !self.available || self.selected == 1 {
            self.sample("changed", self.available);
            return;
        }
        let mut update = self.icon.base();
        update.uFlags = NIF_ICON;
        update.hIcon = self.images[1].0;
        let before = shell_host();
        let ok = self.icon.call("change", NIM_MODIFY, &update);
        if ok {
            // An accepted marker on a replacement Shell cannot establish the original registration's owner.
            self.host.modified(before, shell_host(), |handle| {
                (unsafe { WaitForSingleObject(**handle, 0) }) == WAIT_TIMEOUT
            });
            self.selected = 1;
        }
        self.sample("changed", ok);
    }
}

fn run<T>(
    token: &str,
    menu: &MenuControl,
    language: &TrayLanguage,
    requests: Channel<TrayRequest>,
    ready: SyncSender<bool>,
    deliver: impl Fn(TrayEvent) -> Result<(), TrySendError<T>>,
) -> io::Result<()> {
    let rgb = color(token).map_err(io::Error::other)?;
    let contrast = rgb.map(|channel| 255 - channel);
    let images = [
        image(rgb).map_err(io::Error::other)?,
        image(contrast).map_err(io::Error::other)?,
    ];
    let mut receiver = Receiver::new().map_err(io::Error::other)?;
    let mut tray = Registration {
        icon: Icon {
            owner: &receiver,
            prefix: "gui_tray",
            title: format!("IFW tray {token}"),
            cleanup: false,
        },
        images,
        colors: [rgb, contrast],
        selected: 0,
        available: false,
        host: BoundHost::default(),
    };
    let result: io::Result<()> = (|| {
        // Shell registration can dispatch a callback reentrantly before the message pump starts.
        let mut seen = EVENTS.get();
        let mut recovery = Recovery::new(taskbar());
        // Bootstrap probes the Shell even on a shell-less desktop to establish real fallback.
        let available = tray.register("initial", token)?;
        recovery.result(available, Instant::now());
        tray.sample("initial", available);
        ready.send(available).map_err(io::Error::other)?;
        let mut pending = Pending {
            handled_menu_requests: seen.menu_requests,
            ..Default::default()
        };
        let mut next_host = Instant::now() + Duration::from_secs(1);
        while !menu.stopping.load(Ordering::Acquire) {
            // The window procedure records callbacks only. Delivery and Shell calls happen after dispatch.
            pump_messages(
                if pending.open.is_some() || pending.available.is_some() || pending.menu.is_some() {
                    5
                } else {
                    100
                },
                1,
            );
            let events = EVENTS.get();
            let recreated = events.taskbar != seen.taskbar;
            for (changed, source, ordinal) in [
                (recreated, "unmarked", events.taskbar),
                (
                    events.synthetic_taskbar != seen.synthetic_taskbar,
                    "synthetic",
                    events.synthetic_taskbar,
                ),
            ] {
                if changed {
                    println!(
                        "TRAY_TASKBAR source={source} pid={} hwnd={} ordinal={ordinal}",
                        std::process::id(),
                        receiver.hwnd.0 as usize
                    );
                }
            }
            let now = Instant::now();
            if recreated || now >= next_host {
                next_host = now + Duration::from_secs(1);
                let current = taskbar();
                let previous = recovery.host;
                let was_available = tray.available;
                if current != previous {
                    println!(
                        "TRAY_HOST pid={} previous={} current={} previous_hwnd={} current_hwnd={}",
                        std::process::id(),
                        previous.map_or(0, |h| h.1),
                        current.map_or(0, |h| h.1),
                        previous.map_or(0, |h| h.0),
                        current.map_or(0, |h| h.0)
                    );
                    if current.is_none() {
                        tray.available = false;
                    }
                }
                if let Some(attempt) = recovery.observe(current, recreated, now) {
                    let acknowledged = tray.recover(attempt, token)?;
                    recovery.result(acknowledged, Instant::now());
                }
                if was_available != tray.available {
                    pending.available = Some(tray.available);
                }
            }
            if events.open.ordinal != seen.open.ordinal && tray.available {
                let open = events.open;
                let queued = open
                    .queued_ms
                    .map_or_else(|| "none".into(), |ms| ms.to_string());
                println!(
                    "TRAY_CALLBACK pid={} hwnd={} id={ICON} code={} ordinal={} queued_ms={queued} dispatch_ms={} dispatch_qpc={}",
                    std::process::id(),
                    receiver.hwnd.0 as usize,
                    open.code,
                    open.ordinal,
                    open.dispatch_ms,
                    open.dispatch_qpc
                );
                pending.open = Some(open.ordinal);
            }
            seen = events;
            if pending.take_menu_request(events.menu_requests, tray.available) {
                match menu.select(&tray.icon, language) {
                    Ok(selection) => {
                        pending.menu = selection;
                        // Ignore a second callback received inside modal tracking.
                        pending.handled_menu_requests = EVENTS.get().menu_requests;
                    }
                    Err(error) => eprintln!("Windows tray menu unavailable: {error}"),
                }
            }
            match pending.flush(&deliver) {
                Ok(Some(id)) => println!("TRAY_OPEN pid={} ordinal={id}", std::process::id()),
                Ok(None) | Err(TrySendError::Full(_)) => {}
                Err(TrySendError::Disconnected(_)) => break,
            }
            for request in requests.try_iter().take(8) {
                match request {
                    TrayRequest::Sample => tray.sample("sample", tray.available),
                    TrayRequest::ChangeMarker => tray.change(),
                }
            }
        }
        Ok(())
    })();
    let registered = tray.icon.cleanup;
    let removed = registered && tray.icon.remove("shutdown");
    let retired = registered && !removed && tray.retire_exited_host();
    println!(
        "TRAY_CLEANUP pid={} hwnd={} id={ICON} registered={} removed={}",
        std::process::id(),
        receiver.hwnd.0 as usize,
        u8::from(registered),
        u8::from(removed)
    );
    drop(tray);
    let closed = receiver.close().map_err(io::Error::other);
    result?;
    if registered && !removed && !retired {
        return Err(io::Error::other(
            "The native tray icon could not be removed",
        ));
    }
    closed
}
