//! Exercise the caller's actual portal view using the existing handle-bound filesystem crate.
#![forbid(unsafe_code)]

use safe_fs::{Directory, EntryKind};
use std::error::Error;
use std::ffi::{OsStr, OsString};
use std::io::{ErrorKind, Read, Write};
use std::os::unix::ffi::OsStringExt;
use std::path::{Path, PathBuf};
use std::time::Duration;
use zbus::connection::Builder;

const NAME: &str = "org.freedesktop.portal.Documents";
const OBJECT: &str = "/org/freedesktop/portal/documents";
const APP: &str = "org.example.IfwServices";

fn nonempty_component(value: &str) -> bool {
    !value.is_empty() && Path::new(value).file_name() == Some(OsStr::new(value))
}

fn main() -> Result<(), Box<dyn Error>> {
    if std::env::var("DBUS_SESSION_BUS_ADDRESS").as_deref() != Ok("unix:path=/tmp/session-bus")
        || std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
    {
        return Err("Use a private assessment session".into());
    }
    let args: Vec<_> = std::env::args().skip(1).collect();
    if Path::new("/tmp/producer/source").try_exists()? {
        return Err("The producer was visible to the grant consumer".into());
    }
    let status = std::fs::read_to_string("/proc/self/status")?;
    if !status
        .lines()
        .any(|line| line.starts_with("CapEff:") && line.ends_with("0000000000000000"))
    {
        return Err("The grant consumer retained mount capabilities".into());
    }
    let [id, basename, view] = args.as_slice() else {
        return Err("Expected document ID, basename and test mode".into());
    };
    if !nonempty_component(id) || id == "by-app" || !nonempty_component(basename) {
        return Err("Invalid document component".into());
    }
    let mount = futures_lite::future::block_on(async {
        let bus = Builder::session()?
            .method_timeout(Duration::from_secs(3))
            .build()
            .await?;
        let reply = bus
            .call_method(Some(NAME), OBJECT, Some(NAME), "GetMountPoint", &())
            .await?;
        reply.body().deserialize::<Vec<u8>>()
    })?;
    let bytes = mount
        .strip_suffix(&[0])
        .ok_or("Invalid document mount point")?;
    if bytes.contains(&0) {
        return Err("Invalid document mount point".into());
    }
    let mount = PathBuf::from(OsString::from_vec(bytes.to_vec()));
    let expected =
        PathBuf::from(std::env::var_os("XDG_RUNTIME_DIR").ok_or("Missing private runtime")?)
            .join("doc");
    if mount != expected {
        return Err("Unexpected private portal mount".into());
    }
    let path = mount.join("by-app").join(APP).join(id).join(basename);
    println!("GRANT_PATH {}", path.display());
    if view == "revoked" {
        let error = Directory::open_root(&path)
            .err()
            .ok_or("Revoked document still accessible")?;
        if !matches!(
            error.kind(),
            ErrorKind::NotFound | ErrorKind::PermissionDenied
        ) {
            return Err(error.into());
        }
        println!("REVOKED {error}");
        return Ok(());
    }
    let dir = Directory::open_root(&path)?;
    let entries = dir.entries(32)?;
    if !entries
        .iter()
        .any(|item| item.name == "album" && item.kind == EntryKind::Directory)
    {
        return Err("Granted directory enumeration did not find the synthetic album".into());
    }
    let nested = dir.open_directory(OsStr::new("album"))?;
    println!("ENUMERATED");
    match nested.open_file(OsStr::new("original.jpg")) {
        Ok(mut file) => {
            let mut fixture = String::new();
            (&mut file).take(256).read_to_string(&mut fixture)?;
            if fixture != "Synthetic upload fixture\n" || !file.is_current_entry()? {
                return Err("Granted source or identity mismatch".into());
            }
            println!("READ {:?}", file.identity());
        }
        Err(error) if error.kind() == std::io::ErrorKind::Unsupported => {
            println!("READ_CAPABILITY_REFUSED {error}");
        }
        Err(other) => return Err(other.into()),
    }
    let links = dir.open_directory(OsStr::new("links"))?;
    let traversal = dir
        .open_directory(OsStr::new(".."))
        .err()
        .ok_or("Parent component was accepted")?;
    if traversal.kind() != ErrorKind::InvalidInput {
        return Err(traversal.into());
    }
    // The control resolves entirely inside this synthetic grant. A missing
    // backing path or unsupported media lock cannot satisfy the no-follow check.
    let control = path.join("links/in-grant-link");
    let mut payload = Vec::new();
    std::fs::File::open(&control)?
        .take(64)
        .read_to_end(&mut payload)?;
    if payload != b"Synthetic in-grant link target\n" {
        return Err("Ordinary grant-relative read did not reach the known link target".into());
    }
    for name in ["in-grant-link", "outside-link"] {
        if !path
            .join("links")
            .join(name)
            .symlink_metadata()?
            .is_symlink()
        {
            return Err("Expected an observable synthetic symbolic link".into());
        }
        let refusal = links
            .open_file(OsStr::new(name))
            .err()
            .ok_or("Symbolic link was accepted")?;
        if refusal.kind() != ErrorKind::PermissionDenied || refusal.raw_os_error().is_some() {
            return Err(refusal.into());
        }
        println!("LINK_REFUSED {name} {refusal}");
    }
    println!("TRAVERSAL_REFUSED {traversal}");
    match view.as_str() {
        "read-only" => {
            let error = dir
                .begin_download(OsStr::new("forbidden.jpg"))
                .err()
                .ok_or("Read-only grant accepted a write")?;
            if !matches!(
                error.kind(),
                ErrorKind::PermissionDenied | ErrorKind::ReadOnlyFilesystem
            ) {
                return Err(error.into());
            }
            println!("WRITE_REFUSED {error}");
        }
        "read-write" => {
            let mut transfer = nested.begin_download(OsStr::new("download.jpg"))?;
            transfer.write_all(b"Synthetic download fixture\n")?;
            transfer.publish()?;
            println!("PUBLISHED");
            let mut collision = nested.begin_download(OsStr::new("download.jpg"))?;
            collision.write_all(b"Conflicting fixture\n")?;
            match collision.publish() {
                Err(safe_fs::PublishError::BeforeRename(error))
                    if error.kind() == std::io::ErrorKind::AlreadyExists =>
                {
                    println!("NOREPLACE")
                }
                other => {
                    return Err(format!("Expected pre-rename collision, received {other:?}").into());
                }
            }
            let mut transfer = nested.begin_download(OsStr::new("cancelled.jpg"))?;
            transfer.write_all(b"Cancelled fixture\n")?;
            transfer.cancel()?;
            if nested
                .entries(32)?
                .iter()
                .any(|e| e.name == "cancelled.jpg")
            {
                return Err("Cancelled download became visible".into());
            }
            println!("PUBLISHED_AND_CANCELLED");
        }
        _ => return Err("Expected read-only, read-write or revoked".into()),
    }
    Ok(())
}
