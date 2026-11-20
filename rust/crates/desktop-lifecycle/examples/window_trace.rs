//! Replay the C# view's observations for the headless policy check. Native GUI
//! tests observe the real event loop and window separately.

use desktop_lifecycle::{DesktopLifecycle, HostCommand, TrayAvailability};
use std::io::{self, BufRead};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut policy = DesktopLifecycle::new(true);
    let mut visible = false;
    let mut closed = false;
    for command in io::stdin().lock().lines() {
        let effect = match command?.as_str() {
            "show" => policy.activate(),
            "close" => policy.close_window(),
            "trayAvailable" => policy.tray_result(true),
            "trayUnavailable" => policy.tray_result(false),
            "beginShutdown" => policy.request_quit(),
            "quit" => {
                policy.request_quit();
                policy.background_stopped()
            }
            _ => return Err("unknown lifecycle observation".into()),
        };
        match effect {
            Some(HostCommand::ShowAndFocus) => visible = true,
            Some(HostCommand::Hide) => visible = false,
            Some(HostCommand::ExitEventLoop) => {
                visible = false;
                closed = true;
            }
            Some(HostCommand::StopBackground) | None => (),
        }
        println!(
            "{} {} {}",
            visible,
            closed,
            policy.tray() == TrayAvailability::Unavailable
        );
    }
    Ok(())
}
