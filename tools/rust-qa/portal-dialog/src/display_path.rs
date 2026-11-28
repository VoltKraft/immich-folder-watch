//! Optional display text for a selected directory. All I/O keeps using its grant.
use crate::document_uri::Grant;
use std::collections::HashMap;
use std::ffi::OsStr;
use std::os::unix::ffi::OsStrExt;
use std::path::Path;
use std::time::Duration;
use zbus::Connection;

const DOCUMENTS: &str = "org.freedesktop.portal.Documents";

pub(crate) struct Label {
    pub(crate) text: String,
    pub(crate) source: &'static str,
}

fn host_path(bytes: &[u8]) -> Option<&Path> {
    let bytes = bytes.strip_suffix(&[0]).unwrap_or(bytes);
    let path = Path::new(OsStr::from_bytes(bytes));
    (path.is_absolute() && !bytes.contains(&0)).then_some(path)
}

fn label(path: &Path, source: &'static str) -> Label {
    Label {
        text: path.to_string_lossy().into_owned(),
        source,
    }
}

fn mapped_host(paths: &HashMap<String, Vec<u8>>, grant: &Grant) -> Option<Label> {
    let host = host_path(paths.get(grant.id.to_str()?)?)?;
    if host.file_name()? != grant.root.file_name()? {
        return None;
    }
    Some(subdirectory_label(
        host,
        &grant.relative,
        "Documents.GetHostPaths",
    ))
}

fn subdirectory_label(root: &Path, relative: &Path, source: &'static str) -> Label {
    let mut path = root.to_owned();
    path.extend(relative);
    label(&path, source)
}

async fn query_documents(bus: Option<&Connection>, grant: &Grant) -> Option<Label> {
    let id = grant.id.to_str()?;
    let bus = match bus {
        Some(connection) => connection.clone(),
        None => zbus::connection::Builder::session()
            .ok()?
            .method_timeout(Duration::from_secs(3))
            .build()
            .await
            .ok()?,
    };
    let reply = bus
        .call_method(
            Some(DOCUMENTS),
            "/org/freedesktop/portal/documents",
            Some(DOCUMENTS),
            "GetHostPaths",
            &[id].as_slice(),
        )
        .await
        .ok()?;
    let paths: HashMap<String, Vec<u8>> = reply.body().deserialize().ok()?;
    mapped_host(&paths, grant)
}

async fn deadline() -> Option<Label> {
    async_io::Timer::after(Duration::from_secs(3)).await;
    None
}

pub(crate) async fn probe_documents(bus: Option<&Connection>, grant: &Grant) -> Option<Label> {
    futures_lite::future::or(query_documents(bus, grant), deadline()).await
}

pub(crate) async fn resolve(
    bus: Option<&Connection>,
    grant: &Grant,
    directory: &safe_fs::Directory,
) -> Label {
    // This process handles one picker result. Metadata waits run off the UI
    // thread, and share one deadline with the fallback portal request.
    let lookup = async {
        let directory = directory.clone();
        let attribute = blocking::unblock(move || {
            let mut bytes = [0; 4096];
            let count = directory
                .read_user_attribute(c"user.document-portal.host-path", &mut bytes)
                .ok()?;
            Some(label(host_path(&bytes[..count])?, "xattr"))
        })
        .await;
        if attribute.is_some() {
            return attribute;
        }
        query_documents(bus, grant).await
    };
    futures_lite::future::or(lookup, deadline())
        .await
        .unwrap_or_else(|| label(&grant.path(), "grant"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn host_labels_accept_absolute_unix_bytes_and_an_optional_terminator() {
        assert_eq!(host_path(b"/A %2F\0"), Some(Path::new("/A %2F")));
        assert_eq!(
            host_path(b"/\xff").unwrap().as_os_str().as_bytes(),
            b"/\xff"
        );
        for unusable in [b"".as_slice(), b"relative", b"/partial\0extra", b"/two\0\0"] {
            assert!(host_path(unusable).is_none());
        }
    }

    #[test]
    fn fallback_reply_must_match_the_selected_id_and_basename() {
        let grant =
            crate::document_uri::parse("file:///doc/abc/Test%20%252F", Path::new("/doc")).unwrap();
        let mut paths = HashMap::from([("xyz".to_owned(), b"/albums/Test %2F\0".to_vec())]);
        assert!(mapped_host(&paths, &grant).is_none());
        paths.insert("abc".into(), b"/albums/other".to_vec());
        assert!(mapped_host(&paths, &grant).is_none());
        paths.insert("abc".into(), b"/albums/Test %2F\0".to_vec());
        assert_eq!(
            mapped_host(&paths, &grant).unwrap().text,
            "/albums/Test %2F"
        );
        let nested = Grant::from_path(
            Path::new("/doc/abc/Test %2F/2026/Test %2F"),
            Path::new("/doc"),
        )
        .unwrap();
        assert_eq!(
            mapped_host(&paths, &nested).unwrap().text,
            "/albums/Test %2F/2026/Test %2F"
        );
        paths.insert("abc".into(), b"/albums/2026\0".to_vec());
        assert!(mapped_host(&paths, &nested).is_none());
    }
}
