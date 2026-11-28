//! Read the Linux editor's startup language before its first window or tray menu is created.
use crate::{codec, encoding};
use std::env;
use std::fs::{File, OpenOptions};
use std::io;
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Language {
    English,
    German,
}

impl Language {
    fn system() -> Self {
        // The Unix .NET runtime treats a present, empty LC_ALL or LC_MESSAGES
        // as the invariant UI culture, even when a later variable is German.
        let locale = ["LC_ALL", "LC_MESSAGES", "LANG"]
            .into_iter()
            .find_map(env::var_os);
        let name = locale
            .as_deref()
            .and_then(|value| value.to_str())
            .unwrap_or("");
        let language = name.split(['_', '-', '.', '@']).next().unwrap_or("");
        if language.eq_ignore_ascii_case("de") || language.eq_ignore_ascii_case("deu") {
            Self::German
        } else {
            Self::English
        }
    }
}

/// A missing, blank or unrecognized preference follows the process's startup UI culture.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Preference {
    System,
    Explicit(Language),
}

impl Preference {
    /// Resolve a new selection against the original process UI language.
    pub fn resolve(self, system: Language) -> Language {
        match self {
            Self::System => system,
            Self::Explicit(language) => language,
        }
    }
}

/// The source remains available to distinguish missing configuration from a read or parser error.
#[derive(Debug, PartialEq, Eq)]
pub struct StartupLanguage {
    pub system: Language,
    pub language: Language,
    pub preference: Result<Option<Preference>, codec::Failure>,
}

/// Resolve the same XDG user configuration path as the Linux app without creating directories.
pub fn config_path() -> io::Result<PathBuf> {
    let configured =
        env::var_os("XDG_CONFIG_HOME").filter(|path| !path.to_string_lossy().trim().is_empty());
    let directory = match configured {
        Some(path) => PathBuf::from(path),
        None => env::home_dir()
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "no user home"))?
            .join(".config"),
    };
    Ok(directory.join("immich-folder-watch/config.yaml"))
}

fn read_file(file: File) -> Result<Preference, codec::Failure> {
    if !file
        .metadata()
        .map_err(|e| codec::Failure::InputIo(e.kind()))?
        .is_file()
    {
        return Err(codec::Failure::InputIo(io::ErrorKind::InvalidInput));
    }
    let decoded = encoding::read(file, codec::MAX_FILE_BYTES, codec::MAX_TEXT_BYTES)?;
    let raw = codec::parse(&decoded.text, codec::options(), codec::MAX_TEXT_BYTES)?;
    let value = raw.startup_language().unwrap_or_default();
    let code = value.trim();
    Ok(if code.eq_ignore_ascii_case("en") {
        Preference::Explicit(Language::English)
    } else if code.eq_ignore_ascii_case("de") {
        Preference::Explicit(Language::German)
    } else {
        Preference::System
    })
}

fn preference() -> Result<Option<Preference>, codec::Failure> {
    let path = config_path().map_err(|error| codec::Failure::InputIo(error.kind()))?;
    // A FIFO at the settings path must not hang the desktop startup. Only read the
    // held descriptor after checking that it names a regular file.
    const O_NONBLOCK: i32 = 0x800; // Linux x86_64 and aarch64.
    const O_NOCTTY: i32 = 0x100;
    match OpenOptions::new()
        .read(true)
        .custom_flags(O_NONBLOCK | O_NOCTTY)
        .open(path)
    {
        Ok(file) => read_file(file).map(Some),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(codec::Failure::InputIo(error.kind())),
    }
}

/// Snapshot the system UI language and read the saved preference with the full
/// shipping-format reader. Failed reads fall back to the snapshot and preserve
/// a value-free error for diagnostics.
pub fn load() -> StartupLanguage {
    let system = Language::system();
    let preference = preference();
    let language = match &preference {
        Ok(Some(setting)) => setting.resolve(system),
        _ => system,
    };
    StartupLanguage {
        system,
        language,
        preference,
    }
}
