use super::{Directory, native};
use std::ffi::{OsStr, OsString};
use std::fmt;
use std::fs::File;
use std::io::{self, Write};

/// The point at which a publication failed determines whether the transfer
/// owner must reconcile its durable intent with the filesystem.
#[derive(Debug)]
pub enum PublishError {
    /// A check failed before submitting the native rename. Normal cancellation
    /// can still clean up the private payload.
    BeforeRename(io::Error),
    /// The filesystem may have committed the submitted rename. Retain the
    /// transaction and reconcile the destination before taking another action.
    RenameOutcomeUnknown(io::Error),
    /// The filesystem acknowledged the rename. A later flush or cleanup failed.
    AfterRename(io::Error),
}

impl PublishError {
    /// Whether this attempted publication requires a destination check before
    /// retrying or completing its durable transfer record.
    pub fn requires_reconciliation(&self) -> bool {
        matches!(self, Self::RenameOutcomeUnknown(_) | Self::AfterRename(_))
    }
}

impl fmt::Display for PublishError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::BeforeRename(e) => write!(f, "could not publish staged file: {e}"),
            Self::RenameOutcomeUnknown(e) => {
                write!(
                    f,
                    "rename outcome is unknown and requires reconciliation: {e}"
                )
            }
            Self::AfterRename(e) => {
                write!(f, "file was published and requires reconciliation: {e}")
            }
        }
    }
}

impl std::error::Error for PublishError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::BeforeRename(e) | Self::RenameOutcomeUnknown(e) | Self::AfterRename(e) => Some(e),
        }
    }
}

pub(super) fn transaction_name() -> io::Result<OsString> {
    let random = native::random_bytes()?;
    Ok(format!(".ifw-internal-{:032x}", u128::from_be_bytes(random)).into())
}

#[derive(Debug)]
struct OpenStage {
    file: File,
    directory: native::Transaction,
}

/// Exclusive ownership of a stream in a protected transaction directory.
/// Explicit cancellation reports cleanup errors; dropping the stage also tries
/// to clean it up without reopening arbitrary names.
#[derive(Debug)]
pub struct Download {
    parent: Directory,
    name: OsString,
    open: Option<OpenStage>,
    #[cfg(test)]
    lose_rename_acknowledgement: bool,
}

impl Download {
    pub(super) fn new(parent: &Directory, name: &OsStr) -> io::Result<Self> {
        let directory = native::Transaction::new(parent)?;
        let file = match directory.create_payload() {
            Ok(f) => f,
            Err(e) => {
                let _ = directory.remove_directory();
                return Err(e);
            }
        };
        Ok(Self {
            parent: parent.clone(),
            name: name.into(),
            open: Some(OpenStage { file, directory }),
            #[cfg(test)]
            lose_rename_acknowledgement: false,
        })
    }

    fn open(&self) -> &OpenStage {
        self.open
            .as_ref()
            .expect("only a consumed lease closes its stage")
    }

    pub fn publish(self) -> Result<(), PublishError> {
        let prepared = self.prepare_rename().map_err(PublishError::BeforeRename)?;
        self.submit_rename(prepared)
    }

    fn prepare_rename(&self) -> io::Result<native::RenameName> {
        let stage = self.open();
        stage.file.sync_all()?;
        // An already-occupied name can reject this transfer before submitting
        // any mutation. The native no-replace flag still protects later arrivals.
        match native::entry_info(&self.parent.0.file, &self.name) {
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e),
            Ok(_) => return Err(io::ErrorKind::AlreadyExists.into()),
        }
        stage.directory.prepare_rename(&stage.file, &self.name)
    }

    fn submit_rename(mut self, prepared: native::RenameName) -> Result<(), PublishError> {
        // From submission onwards Drop may only release the OS handles. On
        // Windows disposing the payload by handle could delete its new name
        // after a successful server-side rename with a lost acknowledgement.
        let stage = self.open.take().expect("a prepared stage is still open");
        let acknowledgement =
            stage
                .directory
                .rename_payload(&stage.file, &self.parent.0.file, prepared);
        #[cfg(test)]
        let acknowledgement = acknowledgement.and_then(|()| {
            if self.lose_rename_acknowledgement {
                Err(io::Error::new(
                    io::ErrorKind::ConnectionReset,
                    "lost filesystem acknowledgement",
                ))
            } else {
                Ok(())
            }
        });
        acknowledgement.map_err(PublishError::RenameOutcomeUnknown)?;
        #[cfg(target_os = "linux")]
        let sync = stage.directory.sync_rename(&self.parent.0.file);
        #[cfg(windows)]
        let sync = Ok(());
        drop(stage.file);
        let cleanup = stage.directory.remove_directory();
        sync.and(cleanup).map_err(PublishError::AfterRename)
    }

    pub fn cancel(mut self) -> io::Result<()> {
        self.cancel_private_payload()
    }

    fn cancel_private_payload(&mut self) -> io::Result<()> {
        let Some(stage) = self.open.take() else {
            return Ok(());
        };
        stage.directory.remove_payload(&stage.file)?;
        drop(stage.file);
        stage.directory.remove_directory()
    }
}

impl Write for Download {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        (&self.open().file).write(buf)
    }

    fn flush(&mut self) -> io::Result<()> {
        (&self.open().file).flush()
    }
}

impl Drop for Download {
    fn drop(&mut self) {
        let _ = self.cancel_private_payload();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::Synthetic;
    use std::fs;

    #[test]
    fn lost_acknowledgement_after_native_rename_preserves_destination_and_transaction() {
        let profile = Synthetic::new();
        let root = profile.root();
        let destination = OsStr::new("published");
        let mut download = root.begin_download(destination).unwrap();
        download.write_all(b"committed on the filesystem").unwrap();
        let before = profile.transaction_directories();
        assert_eq!(before.len(), 1);
        download.lose_rename_acknowledgement = true;
        let error = download.publish().unwrap_err();
        assert!(error.requires_reconciliation());
        assert!(
            matches!(error, PublishError::RenameOutcomeUnknown(ref source)
            if source.kind() == io::ErrorKind::ConnectionReset)
        );
        drop(error);
        drop(root);
        // All stage handles and the consumed Download have been dropped.
        assert_eq!(
            fs::read(profile.0.join(destination)).unwrap(),
            b"committed on the filesystem"
        );
        assert_eq!(profile.transaction_directories(), before);
        assert_eq!(fs::read_dir(&before[0]).unwrap().count(), 0);
    }

    #[test]
    fn later_arrival_cannot_be_replaced_after_the_preflight_absence_observation() {
        let profile = Synthetic::new();
        let root = profile.root();
        let destination = OsStr::new("image");
        let mut first = root.begin_download(destination).unwrap();
        first.write_all(b"preserved staged payload").unwrap();
        let stage_dirs = profile.transaction_directories();
        assert_eq!(stage_dirs.len(), 1);
        let prepared = first.prepare_rename().unwrap();

        let mut arrival = root.begin_download(destination).unwrap();
        arrival.write_all(b"published in the meantime").unwrap();
        arrival.publish().unwrap();
        let error = first.submit_rename(prepared).unwrap_err();
        assert!(matches!(error, PublishError::RenameOutcomeUnknown(_)));
        assert!(error.requires_reconciliation());
        assert_eq!(
            fs::read(profile.0.join(destination)).unwrap(),
            b"published in the meantime"
        );
        assert_eq!(
            fs::read(stage_dirs[0].join("payload")).unwrap(),
            b"preserved staged payload"
        );
    }
}
