//! Window and shutdown policy for a per-user desktop process with background work.
//! Native adapters report tray availability and apply commands on the GUI thread.

#![forbid(unsafe_code)]

/// A tray registration becomes available only after the native host acknowledges it.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TrayAvailability {
    Pending,
    Available,
    Unavailable,
}

/// The user's requested window state. Native visibility must be observed separately.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WindowIntent {
    BackgroundStartup,
    Visible,
    HiddenByUser,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Shutdown {
    Running,
    Draining,
    Finished,
}

/// Work requested of the host. A drain only completes when the supervisor joins
/// background tasks and acknowledges all required durable writes.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HostCommand {
    ShowAndFocus,
    Hide,
    StopBackground,
    ExitEventLoop,
}

/// Window reachability is separate from writer ownership and engine state.
#[derive(Debug)]
pub struct DesktopLifecycle {
    window: WindowIntent,
    tray: TrayAvailability,
    shutdown: Shutdown,
}

impl DesktopLifecycle {
    pub fn new(background: bool) -> Self {
        Self {
            window: if background {
                WindowIntent::BackgroundStartup
            } else {
                WindowIntent::Visible
            },
            tray: TrayAvailability::Pending,
            shutdown: Shutdown::Running,
        }
    }

    pub fn window_intent(&self) -> WindowIntent {
        self.window
    }
    pub fn tray(&self) -> TrayAvailability {
        self.tray
    }
    pub fn shutdown(&self) -> Shutdown {
        self.shutdown
    }

    /// Activation must also focus an already visible but obscured window.
    pub fn activate(&mut self) -> Option<HostCommand> {
        if self.shutdown != Shutdown::Running {
            return None;
        }
        self.window = WindowIntent::Visible;
        Some(HostCommand::ShowAndFocus)
    }

    /// Intercept the native close request before the event loop exits.
    pub fn close_window(&mut self) -> Option<HostCommand> {
        if self.shutdown != Shutdown::Running {
            return None;
        }
        self.window = WindowIntent::HiddenByUser;
        Some(HostCommand::Hide)
    }

    /// Only the first registration outcome may reveal a background-started
    /// window. Subsequent tray-host restarts preserve a user's visibility choice.
    pub fn tray_result(&mut self, available: bool) -> Option<HostCommand> {
        let first_result = self.tray == TrayAvailability::Pending;
        self.tray = if available {
            TrayAvailability::Available
        } else {
            TrayAvailability::Unavailable
        };
        if first_result && !available && self.window == WindowIntent::BackgroundStartup {
            self.activate()
        } else {
            None
        }
    }

    pub fn request_quit(&mut self) -> Option<HostCommand> {
        if self.shutdown != Shutdown::Running {
            return None;
        }
        self.shutdown = Shutdown::Draining;
        Some(HostCommand::StopBackground)
    }

    /// Called after durable shutdown. A duplicate or unsolicited completion
    /// must never terminate a running process.
    pub fn background_stopped(&mut self) -> Option<HostCommand> {
        if self.shutdown != Shutdown::Draining {
            return None;
        }
        self.shutdown = Shutdown::Finished;
        Some(HostCommand::ExitEventLoop)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exit_requires_a_requested_and_completed_drain() {
        let mut state = DesktopLifecycle::new(true);
        assert_eq!(state.background_stopped(), None);
        assert_eq!(state.request_quit(), Some(HostCommand::StopBackground));
        assert_eq!(state.request_quit(), None);
        assert_eq!(state.tray_result(false), None);
        assert_eq!(state.activate(), None);
        assert_eq!(state.shutdown(), Shutdown::Draining);
        assert_eq!(state.background_stopped(), Some(HostCommand::ExitEventLoop));
        assert_eq!(state.background_stopped(), None);
        assert_eq!(state.shutdown(), Shutdown::Finished);
    }

    #[test]
    fn repeat_activation_focuses_the_visible_window_without_restarting_background_work() {
        let mut state = DesktopLifecycle::new(false);
        assert_eq!(state.tray_result(false), None);
        assert_eq!(state.activate(), Some(HostCommand::ShowAndFocus));
        assert_eq!(state.activate(), Some(HostCommand::ShowAndFocus));
        assert_eq!(state.close_window(), Some(HostCommand::Hide));
        assert_eq!(state.tray_result(true), None);
        assert_eq!(state.window_intent(), WindowIntent::HiddenByUser);
        assert_eq!(state.shutdown(), Shutdown::Running);
    }
}
