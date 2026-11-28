//! Resolve a FileChooser result inside the application's Documents mount.
use std::ffi::{OsStr, OsString};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::path::{Component, Path, PathBuf};

pub(crate) struct Grant {
    pub(crate) root: PathBuf,
    pub(crate) relative: PathBuf,
    pub(crate) id: OsString,
}

impl Grant {
    pub(crate) fn from_path(path: &Path, mount: &Path) -> Result<Self, &'static str> {
        let raw = path.as_os_str().as_bytes();
        if !mount.is_absolute()
            || raw.contains(&0)
            || raw
                .split(|byte| *byte == b'/')
                .any(|part| matches!(part, b"." | b".."))
        {
            return Err("Expected a normalized Documents path");
        }
        let mut parts = path
            .strip_prefix(mount)
            .map_err(|_| "Path is outside the Documents mount")?
            .components();
        let (Some(Component::Normal(id)), Some(Component::Normal(basename))) =
            (parts.next(), parts.next())
        else {
            return Err("Expected a Documents ID and a granted basename");
        };
        if id == OsStr::new("by-app") {
            return Err("Expected a grant in the application's Documents view");
        }
        Ok(Self {
            root: mount.join(id).join(basename),
            relative: parts.collect(),
            id: id.to_owned(),
        })
    }

    pub(crate) fn path(&self) -> PathBuf {
        let mut path = self.root.clone();
        path.extend(&self.relative);
        path
    }

    pub(crate) fn open(&self) -> std::io::Result<safe_fs::Directory> {
        let mut directory = safe_fs::Directory::open_root(&self.root)?;
        for component in &self.relative {
            directory = directory.open_directory(component)?;
        }
        Ok(directory)
    }
}

fn decode_name(encoded: &str) -> Result<OsString, &'static str> {
    let mut bytes = encoded.bytes();
    let mut name = Vec::with_capacity(encoded.len());
    while let Some(byte) = bytes.next() {
        let byte = if byte == b'%' {
            let mut digit = || {
                bytes
                    .next()
                    .and_then(|b| char::from(b).to_digit(16))
                    .ok_or("Invalid escape in Documents URI")
            };
            (digit()? * 16 + digit()?) as u8
        } else {
            byte
        };
        if matches!(byte, 0 | b'/') {
            return Err("Invalid filename byte in Documents URI");
        }
        name.push(byte);
    }
    if matches!(name.as_slice(), b"" | b"." | b"..") {
        return Err("Expected a filename component in Documents URI");
    }
    Ok(OsString::from_vec(name))
}

pub(crate) fn parse(uri: &str, mount: &Path) -> Result<Grant, &'static str> {
    // The Documents portal returns local, absolute file URIs. Split first so
    // decoding a name cannot introduce path structure or decode a literal % twice.
    let (scheme, hierarchy) = uri.split_once(':').ok_or("Expected a Documents URI")?;
    if !scheme.eq_ignore_ascii_case("file") {
        return Err("Expected a file URI");
    }
    let encoded = if let Some(location) = hierarchy.strip_prefix("//") {
        let (host, path) = location
            .split_once('/')
            .ok_or("Missing Documents URI path")?;
        if !host.is_empty() && !host.eq_ignore_ascii_case("localhost") {
            return Err("Expected a local Documents URI");
        }
        path
    } else {
        hierarchy
            .strip_prefix('/')
            .ok_or("Expected an absolute Documents URI")?
    };
    if encoded.contains(['?', '#']) || !mount.is_absolute() {
        return Err("Expected a Documents URI path and an absolute mount");
    }
    let mut path = PathBuf::from("/");
    for component in encoded.strip_suffix('/').unwrap_or(encoded).split('/') {
        path.push(decode_name(component)?);
    }
    Grant::from_path(&path, mount)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::ffi::OsStrExt;

    #[test]
    fn chooser_names_preserve_literal_percent_and_unix_filename_bytes() {
        let mount = Path::new("/run/user/7/doc");
        for (encoded, name) in [
            ("album", b"album".as_slice()),
            ("Gr%C3%BC%C3%9Fe%20%232%20%252F", "Grüße #2 %2F".as_bytes()),
            ("%ff%3F+%25", b"\xff?+%".as_slice()),
        ] {
            let uri = format!("file:///run/user/7/doc/ab12/{encoded}");
            let grant = parse(&uri, mount).unwrap();
            assert_eq!(grant.id, "ab12");
            assert_eq!(
                grant.path(),
                mount.join("ab12").join(OsStr::from_bytes(name))
            );
        }
    }

    #[test]
    fn grants_require_local_components_under_the_application_mount() {
        let mount = Path::new("/run/user/7/doc");
        for suffix in [
            "by-app/album",
            "id",
            "id/album/child/%2e%2e",
            "id/album/child/a%2Fb",
            "id//album",
            "id/%2e%2e",
            "id/%00",
            "id/a%2Fb",
            "id/a?b",
            "id/a#b",
            "id/%",
            "id/%fg",
        ] {
            assert!(
                parse(&format!("file:///run/user/7/doc/{suffix}"), mount).is_err(),
                "{suffix}"
            );
        }
        assert!(parse("file://host/run/user/7/doc/id/album", mount).is_err());
        assert!(parse("file:///run/user/7/documents/id/album", mount).is_err());
    }

    #[test]
    fn local_directory_uri_spellings_identify_the_same_grant() {
        let mount = Path::new("/run/user/7/doc");
        for uri in [
            "file:/run/user/7/doc/id/album",
            "file:///run/user/7/doc/id/album/",
            "FILE://LOCALHOST/run/user/7/doc/id/album",
        ] {
            assert_eq!(parse(uri, mount).unwrap().path(), mount.join("id/album"));
        }
    }

    #[test]
    fn saved_subdirectory_names_remain_literal_through_both_representations() {
        let mount = Path::new("/run/user/7/doc");
        let path = mount.join("id/Photos/2026/Sommer %2F");
        let saved = Grant::from_path(&path, mount).unwrap();
        let chooser = parse(
            "file:///run/user/7/doc/id/Photos/2026/Sommer%20%252F",
            mount,
        )
        .unwrap();
        for grant in [saved, chooser] {
            assert_eq!(grant.root, mount.join("id/Photos"));
            assert_eq!(grant.relative, Path::new("2026/Sommer %2F"));
            assert_eq!(grant.path(), path);
        }
        for name in ["../Photos", "child/./name", "child/../name"] {
            assert!(Grant::from_path(&mount.join("id/Photos").join(name), mount).is_err());
        }
    }
}
