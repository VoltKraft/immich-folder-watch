//! Refuse an installed Rust assessment before startup when the shipping endpoint is occupied.
use std::fs::{self, File};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

pub(super) const APP: &str = "io.github.voltkraft.immich-folder-watch";
const ENDPOINT: &str = "immich-folder-watch.sock";

pub(super) fn check_installed_runtime() -> io::Result<bool> {
    let declared = std::env::var_os("FLATPAK_ID");
    let metadata = match fs::read_to_string("/.flatpak-info") {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound && declared.is_none() => {
            return Ok(false);
        }
        Err(error) => return Err(error),
    };
    let app = application_name(&metadata)?;
    if declared
        .as_deref()
        .is_some_and(|name| name != std::ffi::OsStr::new(app))
    {
        return Err(io::Error::other(
            "Inconsistent installed application identity",
        ));
    }
    if app != APP {
        return Ok(false);
    }
    let uid = fs::metadata("/proc/self")?.uid();
    let runtime = PathBuf::from(format!("/run/user/{uid}"));
    if std::env::var_os("XDG_RUNTIME_DIR").as_deref() != Some(runtime.as_os_str()) {
        return Err(io::Error::other("Unexpected installed runtime directory"));
    }
    check_directory(&runtime, uid)?;
    Ok(true)
}

fn application_name(metadata: &str) -> io::Result<&str> {
    let mut application = false;
    let mut name = None;
    for line in metadata.lines().map(str::trim) {
        if line.starts_with('[') {
            application = line == "[Application]";
            continue;
        }
        let Some(value) = line.strip_prefix("name=").filter(|_| application) else {
            continue;
        };
        if value.is_empty() || name.replace(value).is_some() {
            return Err(io::Error::other("Invalid installed application name"));
        }
    }
    name.ok_or_else(|| io::Error::other("Missing installed application name"))
}

fn check_directory(path: &Path, uid: u32) -> io::Result<()> {
    let named = fs::symlink_metadata(path)?;
    if !named.is_dir() || named.uid() != uid || named.mode() & 0o777 != 0o700 {
        return Err(io::Error::other(
            "Expected the private current-user Flatpak runtime directory",
        ));
    }
    let directory = File::open(path)?;
    let opened = directory.metadata()?;
    if (named.dev(), named.ino()) != (opened.dev(), opened.ino()) {
        return Err(io::Error::other(
            "Installed runtime directory changed before observation",
        ));
    }
    // Resolve this one name through the pinned directory. Never connect, write or remove the entry.
    let pinned = PathBuf::from(format!("/proc/self/fd/{}", directory.as_raw_fd()));
    check_endpoint(&pinned, &opened)
}

fn check_endpoint(pinned: &Path, expected: &fs::Metadata) -> io::Result<()> {
    let verify_anchor = || {
        let anchor = fs::metadata(pinned)?;
        if !anchor.is_dir() || (anchor.dev(), anchor.ino()) != (expected.dev(), expected.ino()) {
            return Err(io::Error::other(
                "Cannot resolve the private runtime directory through its handle",
            ));
        }
        Ok(())
    };
    verify_anchor()?;
    match fs::symlink_metadata(pinned.join(ENDPOINT)) {
        Ok(_) => Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "Shipping activation endpoint is occupied. Startup refused.",
        )),
        Err(error) if error.kind() == io::ErrorKind::NotFound => verify_anchor(),
        Err(error) => Err(error),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{DirBuilderExt, symlink};
    use std::os::unix::net::UnixListener;

    #[test]
    fn application_identity_uses_the_application_section() {
        assert_eq!(application_name("[Application]\nruntime=runtime/example\nname=org.example.Test\n[Instance]\nname=other").unwrap(), "org.example.Test");
        assert!(application_name("[Instance]\nname=other").is_err());
        assert!(application_name("[Application]\nname=one\nname=two").is_err());
    }

    #[test]
    fn refuses_occupied_entries_without_touching_their_identity() -> io::Result<()> {
        let path = std::env::temp_dir().join(format!("ifw-legacy-{}", std::process::id()));
        fs::DirBuilder::new().mode(0o700).create(&path)?;
        let uid = fs::metadata(&path)?.uid();
        check_directory(&path, uid)?;
        let expected = fs::metadata(&path)?;
        assert!(check_endpoint(&path.join("missing"), &expected).is_err());
        assert!(check_endpoint(path.parent().unwrap(), &expected).is_err());
        let leaf = path.join(ENDPOINT);
        let listener = UnixListener::bind(&leaf)?;
        let inode = leaf.symlink_metadata()?.ino();
        assert_eq!(
            check_directory(&path, uid).unwrap_err().kind(),
            io::ErrorKind::AlreadyExists
        );
        drop(listener);
        assert_eq!(
            check_directory(&path, uid).unwrap_err().kind(),
            io::ErrorKind::AlreadyExists
        );
        assert_eq!(leaf.symlink_metadata()?.ino(), inode);
        fs::remove_file(&leaf)?;
        symlink("absent", &leaf)?;
        assert_eq!(
            check_directory(&path, uid).unwrap_err().kind(),
            io::ErrorKind::AlreadyExists
        );
        assert_eq!(leaf.read_link()?, PathBuf::from("absent"));
        fs::remove_file(&leaf)?;
        fs::remove_dir(path)
    }
}
