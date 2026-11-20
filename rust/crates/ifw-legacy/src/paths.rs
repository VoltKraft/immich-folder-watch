//! Legacy database path normalization, never filesystem authorization.
//!
//! These lexical/native string operations do not open files, follow symlinks or
//! bind a watch-root handle. Sensitive operations must independently use `safe-fs`.
//! Paths are kept as OS strings; callers must not replace encoding errors with
//! lossy strings when persisting or comparing identities.

use std::path::{Component, Path, PathBuf};

#[derive(Debug)]
pub enum PathCodecError {
    RequiresAbsolute,
    RequiresRelative,
    EmptyOrNul,
    UnsupportedWindowsNamespace,
    Native(std::io::Error),
}

impl std::fmt::Display for PathCodecError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::RequiresAbsolute => "legacy source requires an explicit absolute path",
            Self::RequiresRelative => "legacy file key requires a relative path",
            Self::EmptyOrNul => "legacy path is empty or contains NUL",
            Self::UnsupportedWindowsNamespace => {
                "Windows device/verbatim namespace is not qualified"
            }
            Self::Native(_) => "native path expansion failed",
        })
    }
}

impl std::error::Error for PathCodecError {}

/// Normalize an already absolute source using native legacy spelling rules.
/// Relative configuration paths must first be resolved against an explicit profile
/// directory; this API refuses an implicit process-current-directory dependency.
#[cfg(unix)]
pub fn normalize_absolute_source(path: &Path) -> Result<PathBuf, PathCodecError> {
    use std::os::unix::ffi::OsStrExt;
    if path.as_os_str().as_bytes().contains(&0) || path.as_os_str().is_empty() {
        return Err(PathCodecError::EmptyOrNul);
    }
    if !path.is_absolute() {
        return Err(PathCodecError::RequiresAbsolute);
    }
    let mut output = PathBuf::from("/");
    for component in path.components() {
        match component {
            Component::RootDir | Component::CurDir => {}
            Component::ParentDir => {
                output.pop();
            }
            Component::Normal(value) => output.push(value),
            Component::Prefix(_) => return Err(PathCodecError::RequiresAbsolute),
        }
    }
    Ok(output)
}

/// Windows expansion delegates to Rust's pinned native GetFullPathNameW-backed
/// implementation. Verbatim/device namespaces await a separate qualification.
#[cfg(windows)]
pub fn normalize_absolute_source(path: &Path) -> Result<PathBuf, PathCodecError> {
    use std::ffi::OsString;
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use std::path::Prefix;
    let units: Vec<u16> = path.as_os_str().encode_wide().collect();
    if units.is_empty() || units.contains(&0) {
        return Err(PathCodecError::EmptyOrNul);
    }
    if !path.is_absolute() {
        return Err(PathCodecError::RequiresAbsolute);
    }
    if !matches!(path.components().next(), Some(Component::Prefix(prefix))
        if matches!(prefix.kind(), Prefix::Disk(_) | Prefix::UNC(_, _)))
    {
        return Err(PathCodecError::UnsupportedWindowsNamespace);
    }
    let absolute = std::path::absolute(path).map_err(PathCodecError::Native)?;
    let mut output: Vec<u16> = absolute.as_os_str().encode_wide().collect();
    // .NET's UNC root excludes the final separator; a drive root includes it.
    let drive_root =
        output.len() == 3 && output[1] == u16::from(b':') && output[2] == u16::from(b'\\');
    if !drive_root && matches!(output.last(), Some(47 | 92)) {
        output.pop();
    }
    Ok(PathBuf::from(OsString::from_wide(&output)))
}

/// Match the legacy relative-key spelling without resolving dot components.
/// This function does not authorize traversal; the storage key is only an identity.
pub fn normalize_relative_text(input: &str) -> Result<String, PathCodecError> {
    if input.trim().is_empty() || input.contains('\0') {
        return Err(PathCodecError::EmptyOrNul);
    }
    if Path::new(input).has_root() {
        return Err(PathCodecError::RequiresRelative);
    }
    #[cfg(windows)]
    {
        if matches!(
            Path::new(input).components().next(),
            Some(Component::Prefix(_))
        ) || input.as_bytes().get(1) == Some(&b':')
        {
            return Err(PathCodecError::RequiresRelative);
        }
        Ok(input.replace('/', "\\"))
    }
    #[cfg(not(windows))]
    {
        Ok(input.to_owned())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_requires_explicit_base_and_relative_keys_preserve_dot_segments() {
        assert!(normalize_absolute_source(Path::new("relative/path")).is_err());
        assert!(normalize_absolute_source(Path::new("\0")).is_err());
        assert!(normalize_relative_text("  ").is_err());
        assert!(normalize_relative_text("/rooted.jpg").is_err());
        assert_eq!(
            normalize_relative_text("../file.jpg").unwrap(),
            if cfg!(windows) {
                "..\\file.jpg"
            } else {
                "../file.jpg"
            }
        );
    }

    #[test]
    #[cfg(unix)]
    fn unix_source_normalization_is_lexical_and_preserves_nonunicode_bytes() {
        use std::ffi::OsString;
        use std::os::unix::ffi::OsStringExt;
        assert_eq!(
            normalize_absolute_source(Path::new("/a//b/../../..")).unwrap(),
            PathBuf::from("/")
        );
        let input = PathBuf::from(OsString::from_vec(b"/synthetic/\xff/../\xfe".to_vec()));
        let expected = PathBuf::from(OsString::from_vec(b"/synthetic/\xfe".to_vec()));
        assert_eq!(normalize_absolute_source(&input).unwrap(), expected);
    }

    #[test]
    #[cfg(windows)]
    fn windows_drive_and_unc_root_spelling_matches_reference() {
        assert_eq!(
            normalize_absolute_source(Path::new(r"C:\")).unwrap(),
            PathBuf::from(r"C:\")
        );
        assert_eq!(
            normalize_absolute_source(Path::new(r"\\server.invalid\share\")).unwrap(),
            PathBuf::from(r"\\server.invalid\share")
        );
        assert!(normalize_relative_text("C:drive-relative.jpg").is_err());
        assert!(normalize_absolute_source(Path::new(r"\\?\C:\synthetic")).is_err());
    }
}
