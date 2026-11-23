//! Read a single synthetic source through the installed Flatpak's own Documents grant.
#![forbid(unsafe_code)]

use safe_fs::Directory;
use std::ffi::OsStr;
use std::fs;
use std::io::{self, BufRead, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};

const APP: &str = "org.example.IfwPortalLease";

fn application_name(metadata: &str) -> Option<&str> {
    let mut application = false;
    let mut name = None;
    for line in metadata.lines() {
        if line.starts_with('[') {
            application = line == "[Application]";
        } else if application && let Some(value) = line.strip_prefix("name=") {
            if name.is_some() {
                return None;
            }
            name = Some(value);
        }
    }
    name
}

fn sandbox(phase: &str) -> io::Result<PathBuf> {
    if std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
        || std::env::var("FLATPAK_ID").as_deref() != Ok(APP)
        || application_name(&fs::read_to_string("/.flatpak-info")?) != Some(APP)
        || std::env::current_exe()? != Path::new("/app/bin/reader")
    {
        return Err(io::Error::other("Expected the installed test application"));
    }
    let status = fs::read_to_string("/proc/self/status")?;
    let ids = status
        .lines()
        .find_map(|line| line.strip_prefix("Uid:"))
        .ok_or_else(|| io::Error::other("Missing process identity"))?
        .split_whitespace()
        .collect::<Vec<_>>();
    if ids.len() != 4
        || ids[0].parse::<u32>().ok().filter(|uid| *uid > 0).is_none()
        || ids.iter().any(|id| *id != ids[0])
    {
        return Err(io::Error::other("Expected an ordinary test user"));
    }
    let runtime = format!("/run/user/{}", ids[0]);
    let mount = format!("{runtime}/doc");
    if std::env::var("XDG_RUNTIME_DIR").as_deref() != Ok(runtime.as_str()) {
        return Err(io::Error::other(format!(
            "Unexpected application runtime: {:?}",
            std::env::var("XDG_RUNTIME_DIR")
        )));
    }
    let mounts = fs::read_to_string("/proc/self/mountinfo")?;
    let visible: Vec<_> = mounts
        .lines()
        .filter(|row| row.contains(" - fuse.portal "))
        .collect();
    let resolved = fs::canonicalize(&mount).map_err(|error| {
        io::Error::other(format!(
            "Cannot resolve {mount}: {error}; portal mount records {visible:?}"
        ))
    })?;
    if !visible
        .iter()
        .any(|row| row.split_whitespace().nth(4) == resolved.to_str())
    {
        return Err(io::Error::other(format!(
            "Documents path {mount} resolves to {resolved:?}; portal mount records {visible:?}"
        )));
    }
    let direct = format!("/home/ifwqa/ifw-portal-{phase}/source/album/original.jpg");
    let err = fs::File::open(direct)
        .err()
        .ok_or_else(|| io::Error::other("The sandbox can access the backing file directly"))?;
    let direct_errno = err.raw_os_error().unwrap_or(0);
    if !matches!(direct_errno, 2 | 13) {
        return Err(err);
    }
    println!(
        "SANDBOX uid={} mount=fuse.portal direct_errno={direct_errno}",
        ids[0]
    );
    Ok(PathBuf::from(mount))
}

fn report(line: &str) -> io::Result<()> {
    println!("{line}");
    io::stdout().flush()
}

// Independent syscall control on the same granted synthetic name. It does
// not provide data to the normal reader. Parent descriptors remain pinned.
fn lock_control(root: &Path) -> io::Result<i32> {
    const O_DIRECTORY: i32 = 0x10000;
    const O_NOFOLLOW: i32 = 0x20000;
    const O_NONBLOCK: i32 = 0x800;
    let directory = |p: &Path| {
        fs::OpenOptions::new()
            .read(true)
            .custom_flags(O_DIRECTORY | O_NOFOLLOW)
            .open(p)
    };
    let child = |parent: &fs::File, name: &str| {
        PathBuf::from(format!("/proc/self/fd/{}", parent.as_raw_fd())).join(name)
    };
    let dir = directory(root)?;
    let album = directory(&child(&dir, "album"))?;
    let target = fs::OpenOptions::new()
        .read(true)
        .custom_flags(O_NOFOLLOW | O_NONBLOCK)
        .open(child(&album, "original.jpg"))?;
    if !target.metadata()?.is_file() {
        return Err(io::Error::other("Expected the synthetic regular file"));
    }
    match target.try_lock_shared() {
        Ok(()) => report("LOCK_CONTROL acquired")?,
        Err(std::fs::TryLockError::Error(e)) => {
            report(&format!(
                "LOCK_CONTROL errno={}",
                e.raw_os_error().unwrap_or(0)
            ))?;
        }
        Err(std::fs::TryLockError::WouldBlock) => report("LOCK_CONTROL contended")?,
    }
    Ok(0)
}

fn run() -> io::Result<i32> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [mode, document, phase] = args.as_slice() else {
        return Err(io::Error::other("Expected mode, document ID and phase"));
    };
    if !matches!(mode.as_str(), "read" | "hold" | "lock-control")
        || !matches!(phase.as_str(), "stock" | "candidate" | "restored")
        || document.is_empty()
        || document.len() > 32
        || !document
            .bytes()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
    {
        return Err(io::Error::other("Unexpected synthetic test arguments"));
    }
    let root = sandbox(phase)?.join(document).join("source");
    if mode == "lock-control" {
        return lock_control(&root);
    }
    let dir = match Directory::open_root(&root) {
        Ok(directory) => directory,
        Err(error) => {
            report(&format!(
                "NO_GRANT root_errno={}",
                error.raw_os_error().unwrap_or(0)
            ))?;
            return Ok(21);
        }
    };
    let album = dir.open_directory(OsStr::new("album"))?;
    let mut file = match album.open_file(OsStr::new("original.jpg")) {
        Ok(file) => file,
        Err(error) => {
            let reason = if error.kind() == io::ErrorKind::WouldBlock {
                "contended".to_string()
            } else {
                format!("errno={}", error.raw_os_error().unwrap_or(0))
            };
            report(&format!("REFUSED lease={reason}"))?;
            return Ok(20);
        }
    };
    let mut contents = Vec::new();
    (&mut file).take(64).read_to_end(&mut contents)?;
    if contents != b"Synthetic upload fixture\n" || !file.is_current_entry()? {
        return Err(io::Error::other(
            "Unexpected granted contents or file identity",
        ));
    }
    report(&format!(
        "ACQUIRED bytes={} identity={:?}",
        contents.len(),
        file.identity()
    ))?;
    if mode == "hold"
        && io::stdin().lock().lines().next().transpose()?.as_deref() != Some("release")
    {
        return Err(io::Error::other("Expected the holder release"));
    }
    drop(file);
    Ok(0)
}

fn main() {
    match run() {
        Ok(status) => std::process::exit(status),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn selects_only_the_application_name() {
        assert_eq!(
            application_name("[Application]\nname=reader\n[Instance]\nname=other"),
            Some("reader")
        );
        assert_eq!(application_name("[Runtime]\nname=reader"), None);
        assert_eq!(
            application_name("[Application]\nname=reader\nname=other"),
            None
        );
    }
}
