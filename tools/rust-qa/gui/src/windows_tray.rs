//! Own the elected GUI's notification icon independently of its eframe window generations.
use crate::windows_tray_shell::{EVENTS, ICON, Icon, Image, Receiver, color, image, pump_messages};
use crate::windows_tray_state::{Pending, TrayEvent};
use std::io;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver as Channel, SyncSender, TrySendError, sync_channel};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use windows::Win32::UI::Shell::*;
use windows::Win32::UI::WindowsAndMessaging::*;
use windows::core::w;

#[derive(Clone, Copy)]
pub enum TrayRequest {
    ChangeMarker,
    Sample,
}

pub struct NativeTray {
    pub requests: SyncSender<TrayRequest>,
    stopping: Arc<AtomicBool>,
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
        let stopping = Arc::new(AtomicBool::new(false));
        let stop = Arc::clone(&stopping);
        let thread = thread::Builder::new()
            .name("native-tray".into())
            .spawn(move || run(&token, &stop, input, ready, deliver))?;
        let mut tray = Self {
            requests,
            stopping,
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
        self.stopping.store(true, Ordering::Release);
        if let Some(thread) = self.thread.take() {
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

fn taskbar() -> Option<(usize, u32)> {
    // Observe only the notification host on the receiver's desktop.
    unsafe {
        let bar = FindWindowW(w!("Shell_TrayWnd"), None).ok()?;
        let mut pid = 0;
        GetWindowThreadProcessId(bar, Some(&mut pid));
        (pid != 0).then_some((bar.0 as usize, pid))
    }
}

struct Registration<'a> {
    icon: Icon<'a>,
    images: [Image; 2],
    colors: [[u8; 3]; 2],
    selected: usize,
    available: bool,
}

impl Registration<'_> {
    fn register(&mut self, phase: &str, token: &str) -> io::Result<bool> {
        let (added, v4) = self.icon.register(phase, self.images[self.selected].0);
        println!(
            "TRAY_REGISTER phase={phase} pid={} hwnd={} id={ICON} token={token} added={} version4={}",
            std::process::id(),
            self.icon.owner.hwnd.0 as usize,
            u8::from(added),
            u8::from(v4)
        );
        self.available = added && v4;
        if added && !v4 && !self.icon.remove("incompatible_version") {
            return Err(io::Error::other("Failed to withdraw the rejected v4 icon"));
        }
        Ok(self.available)
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
        let mut update = self.icon.base();
        update.uFlags = NIF_ICON;
        update.hIcon = self.images[1].0;
        let ok =
            self.available && (self.selected == 1 || self.icon.call("change", NIM_MODIFY, &update));
        if ok {
            self.selected = 1;
        }
        self.sample("changed", ok);
    }
}

fn run<T>(
    token: &str,
    stopping: &AtomicBool,
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
    };
    let result: io::Result<()> = (|| {
        let mut host = taskbar();
        let available = tray.register("initial", token)?;
        tray.sample("initial", available);
        ready.send(available).map_err(io::Error::other)?;
        let mut pending = Pending::default();
        let mut seen = EVENTS.get();
        let mut next_host = Instant::now() + Duration::from_secs(1);
        let mut retry =
            (!available && host.is_some()).then(|| Instant::now() + Duration::from_secs(3));
        while !stopping.load(Ordering::Acquire) {
            // The window procedure records callbacks only. Delivery and Shell calls happen after dispatch.
            pump_messages(
                if pending.open.is_some() || pending.available.is_some() {
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
                let replaced = current != host;
                if replaced {
                    println!(
                        "TRAY_HOST pid={} previous={} current={} previous_hwnd={} current_hwnd={}",
                        std::process::id(),
                        host.map_or(0, |h| h.1),
                        current.map_or(0, |h| h.1),
                        host.map_or(0, |h| h.0),
                        current.map_or(0, |h| h.0)
                    );
                    if host.is_some() && (current.is_none() || tray.icon.rect().is_err()) {
                        tray.available = false;
                        pending.available = Some(false);
                    }
                    host = current;
                }
                let due = retry.is_some_and(|time| now >= time);
                if recreated || (replaced && current.is_some()) || due {
                    retry = None;
                    if !tray.available || tray.icon.rect().is_err() {
                        pending.available =
                            Some(tray.register(if due { "retry" } else { "recreate" }, token)?);
                    }
                }
            }
            if events.open.ordinal != seen.open.ordinal && tray.available {
                let open = events.open;
                let queued = open
                    .queued_ms
                    .map_or_else(|| "none".into(), |ms| ms.to_string());
                println!(
                    "TRAY_CALLBACK pid={} hwnd={} id={ICON} code={} ordinal={} queued_ms={queued} dispatch_ms={}",
                    std::process::id(),
                    receiver.hwnd.0 as usize,
                    open.code,
                    open.ordinal,
                    open.dispatch_ms
                );
                pending.open = Some(open.ordinal);
            }
            seen = events;
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
    if registered && !removed {
        return Err(io::Error::other(
            "The native tray icon could not be removed",
        ));
    }
    closed
}
