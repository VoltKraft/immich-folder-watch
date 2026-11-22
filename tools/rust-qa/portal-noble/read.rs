//! Exercise the shipping Rust read lease on one fixed synthetic regular file.
#![forbid(unsafe_code)]
use safe_fs::{Directory, VerifiedFile};
use std::ffi::OsStr;
use std::io::{self, BufRead, Read, Write};
use std::path::Path;

fn refusal(error: &io::Error) -> String {
    // This development protocol classifies failures from the normal Linux
    // read-lease acquisition only. It neither substitutes a lock nor retries
    // through another path. Keep the native errno when Rust preserves it.
    let (outcome, action) = match error.raw_os_error() {
        Some(38 | 95) => ("UnsupportedFileLock", "CheckPortalFileLockSupport"),
        Some(11) => ("FileBusy", "RetryAfterWriterRelease"),
        Some(1 | 13) => ("AccessDenied", "RestoreAuthorizedAccess"),
        _ if error.kind() == io::ErrorKind::WouldBlock => ("FileBusy", "RetryAfterWriterRelease"),
        _ if error.kind() == io::ErrorKind::PermissionDenied => {
            ("AccessDenied", "RestoreAuthorizedAccess")
        }
        _ => ("ReadLeaseUnavailable", "InspectNativeError"),
    };
    let native = error.raw_os_error().map_or_else(
        || format!("kind={:?}", error.kind()),
        |number| format!("errno={number}"),
    );
    format!("REFUSED {native} operation=ReadLease outcome={outcome} action={action}")
}

fn emit(line: &str) -> io::Result<()> {
    println!("{line}");
    io::stdout().flush()
}

fn acquire(album: &Directory) -> io::Result<Option<VerifiedFile>> {
    let mut file = match album.open_file(OsStr::new("original.jpg")) {
        Ok(file) => file,
        Err(error) => {
            emit(&refusal(&error))?;
            return Ok(None);
        }
    };
    let mut contents = Vec::new();
    (&mut file).take(64).read_to_end(&mut contents)?;
    if contents != b"Synthetic upload fixture\n" || !file.is_current_entry()? {
        return Err(io::Error::other("Unexpected synthetic regular file"));
    }
    Ok(Some(file))
}

fn run() -> io::Result<i32> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [mode, root] = args.as_slice() else {
        return Err(io::Error::other(
            "Expected read, hold or retry and a fixture root",
        ));
    };
    if std::env::var("IFW_QA_ISOLATED").as_deref() != Ok("1")
        || !matches!(mode.as_str(), "read" | "hold" | "retry")
        || !(root == "/tmp/producer/source"
            || (root.starts_with("/run/user/0/doc/by-app/org.example.IfwServices/")
                && Path::new(root).file_name() == Some(OsStr::new("source"))))
    {
        return Err(io::Error::other("Expected the private Documents fixture"));
    }
    let dir = Directory::open_root(Path::new(root))?;
    let album = dir.open_directory(OsStr::new("album"))?;
    if mode == "retry" {
        // The three explicit attempts share these retained directory handles.
        // A failed acquisition returns no file lease; only the caller can
        // request another acquisition, and it cannot replace this root.
        emit(&format!("READY pid={} attempts=3", std::process::id()))?;
        let mut commands = io::stdin().lock().lines();
        for _ in 0..3 {
            if commands.next().transpose()?.as_deref() != Some("attempt") {
                return Err(io::Error::other("Missing bounded retry control"));
            }
            if let Some(file) = acquire(&album)? {
                let report = format!("ACQUIRED identity={:?}", file.identity());
                drop(file);
                emit(&report)?;
            }
        }
        if commands.next().transpose()?.as_deref() != Some("stop") {
            return Err(io::Error::other("Missing retry stop control"));
        }
        return Ok(0);
    }
    let Some(file) = acquire(&album)? else {
        return Ok(20);
    };
    emit(&format!("ACQUIRED identity={:?}", file.identity()))?;
    if mode == "hold"
        && io::stdin().lock().lines().next().transpose()?.as_deref() != Some("release")
    {
        return Err(io::Error::other("Missing holder release"));
    }
    Ok(0)
}

fn main() {
    match run() {
        Ok(status) => std::process::exit(status),
        Err(error) => {
            // Setup, content and identity failures are not lock diagnoses.
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unsupported_lock_preserves_errno_and_names_the_capability() {
        for number in [38, 95] {
            let report = refusal(&io::Error::from_raw_os_error(number));
            assert!(report.contains(&format!("errno={number} ")));
            assert!(
                report.contains("outcome=UnsupportedFileLock action=CheckPortalFileLockSupport")
            );
            assert!(!report.contains("FileBusy"));
        }
    }

    #[test]
    fn contention_keeps_native_or_normalized_error_and_a_distinct_action() {
        for (error, native) in [
            (io::Error::from_raw_os_error(11), "errno=11"),
            (
                io::Error::from(io::ErrorKind::WouldBlock),
                "kind=WouldBlock",
            ),
        ] {
            let report = refusal(&error);
            assert!(report.contains(native));
            assert!(report.contains("outcome=FileBusy action=RetryAfterWriterRelease"));
            assert!(!report.contains("UnsupportedFileLock"));
        }
    }

    #[test]
    fn denial_is_neither_contention_nor_an_unsupported_lock() {
        for number in [1, 13] {
            let report = refusal(&io::Error::from_raw_os_error(number));
            assert!(report.contains(&format!("errno={number} ")));
            assert!(report.contains("outcome=AccessDenied action=RestoreAuthorizedAccess"));
            assert!(!report.contains("UnsupportedFileLock"));
            assert!(!report.contains("FileBusy"));
        }
    }

    #[test]
    fn unknown_error_does_not_invent_a_lock_capability_diagnosis() {
        for error in [
            io::Error::from_raw_os_error(5),
            io::Error::from(io::ErrorKind::Unsupported),
        ] {
            assert!(
                refusal(&error).contains("outcome=ReadLeaseUnavailable action=InspectNativeError")
            );
        }
    }
}
