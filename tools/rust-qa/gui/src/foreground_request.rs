//! An explicit activation survives creation of a new native root until it becomes visible.
use desktop_lifecycle::HostCommand;

#[derive(Default)]
pub(super) struct ForegroundRequest {
    pending: bool,
}

impl ForegroundRequest {
    pub(super) fn update(&mut self, explicit_open: bool, action: Option<HostCommand>) {
        match action {
            Some(HostCommand::ShowAndFocus) if explicit_open => self.pending = true,
            Some(HostCommand::Hide | HostCommand::StopBackground) => self.pending = false,
            _ => (),
        }
    }

    /// Consume before entering the native focus call, including when Windows denies it.
    pub(super) fn take_visible<T>(
        &mut self,
        visible_root: impl FnOnce() -> Option<T>,
    ) -> Option<T> {
        if !self.pending {
            return None;
        }
        let root = visible_root()?;
        self.pending = false;
        Some(root)
    }
}
