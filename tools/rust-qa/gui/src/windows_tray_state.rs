//! Coalesce native tray events until the GUI's bounded command queue accepts them.
use std::sync::mpsc::TrySendError;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TrayEvent {
    Availability(bool),
    Open,
}

#[derive(Default)]
pub(crate) struct Pending {
    pub(crate) available: Option<bool>,
    pub(crate) open: Option<u32>,
}

impl Pending {
    pub(crate) fn flush<T>(
        &mut self,
        send: &impl Fn(TrayEvent) -> Result<(), TrySendError<T>>,
    ) -> Result<Option<u32>, TrySendError<T>> {
        if let Some(available) = self.available {
            send(TrayEvent::Availability(available))?;
            self.available = None;
        }
        if let Some(ordinal) = self.open {
            send(TrayEvent::Open)?;
            self.open = None;
            return Ok(Some(ordinal));
        }
        Ok(None)
    }
}
