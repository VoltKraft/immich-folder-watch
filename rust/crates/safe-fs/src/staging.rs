use super::{Directory, native};
use std::ffi::{OsStr, OsString};
use std::fmt;
use std::fs::File;
use std::io::{self, Write};

/// Distinguish a rejected publication from a visible rename followed by a
/// durability or cleanup error. Retrying the transfer requires reconciliation
/// when its destination has already appeared.
#[derive(Debug)]
pub enum PublishError {
    BeforeRename(io::Error),
    AfterRename(io::Error),
}

impl fmt::Display for PublishError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::BeforeRename(e) => write!(f, "could not publish staged file: {e}"),
            Self::AfterRename(e) => {
                write!(f, "file was published and requires reconciliation: {e}")
            }
        }
    }
}

impl std::error::Error for PublishError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::BeforeRename(e) | Self::AfterRename(e) => Some(e),
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
        })
    }

    fn open(&self) -> &OpenStage {
        self.open
            .as_ref()
            .expect("only a consumed lease closes its stage")
    }

    pub fn publish(mut self) -> Result<(), PublishError> {
        let stage = self.open();
        stage.file.sync_all().map_err(PublishError::BeforeRename)?;
        stage
            .directory
            .rename_payload(&stage.file, &self.parent.0.file, &self.name)
            .map_err(PublishError::BeforeRename)?;
        #[cfg(target_os = "linux")]
        let sync = stage.directory.sync_rename(&self.parent.0.file);
        #[cfg(windows)]
        let sync = Ok(());
        let cleanup = self.close(true);
        sync.and(cleanup).map_err(PublishError::AfterRename)
    }

    pub fn cancel(mut self) -> io::Result<()> {
        self.close(false)
    }

    fn close(&mut self, published: bool) -> io::Result<()> {
        let Some(stage) = self.open.take() else {
            return Ok(());
        };
        if !published {
            stage.directory.remove_payload(&stage.file)?;
        }
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
        let _ = self.close(false);
    }
}
