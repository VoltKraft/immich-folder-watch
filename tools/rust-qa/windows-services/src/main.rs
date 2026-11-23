//! Native Windows shell service assessment on a disposable user profile.

#[cfg(windows)]
mod shortcuts;
#[cfg(windows)]
mod toast;
#[cfg(any(windows, test))]
mod toast_readiness;
#[cfg(windows)]
mod tray;

#[cfg(windows)]
use std::{ffi::OsStr, os::windows::ffi::OsStrExt, path::Path};
#[cfg(windows)]
use windows::core::{Error, HRESULT, Result};

#[cfg(windows)]
fn wide(value: &OsStr) -> Vec<u16> {
    value.encode_wide().chain(Some(0)).collect()
}

#[cfg(windows)]
fn invalid() -> Error {
    Error::from_hresult(HRESULT(0x8007_0057_u32 as i32))
}

#[cfg(windows)]
fn hosted() -> bool {
    std::env::var("GITHUB_ACTIONS").as_deref() == Ok("true")
        && std::env::var("RUNNER_ENVIRONMENT").as_deref() == Ok("github-hosted")
        && std::env::var("RUNNER_OS").as_deref() == Ok("Windows")
}

#[cfg(windows)]
fn run() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    // Both temporary shortcut targets exit without opening or changing a profile.
    if args.as_slice() == [OsStr::new("--autostart")]
        || args.as_slice() == [OsStr::new("--toast-shortcut")]
    {
        return Ok(());
    }
    let [mode, directory, id, known] = args.as_slice() else {
        return Err(invalid());
    };
    let id = id.to_str().ok_or_else(invalid)?;
    let area = Path::new(directory);
    if id.len() != 32
        || !id.bytes().all(|b| b.is_ascii_hexdigit())
        || !area.is_absolute()
        || area.file_name() != Some(OsStr::new(&format!("ifw-shell-{id}")))
        || std::fs::read_to_string(area.join("synthetic.fixture"))
            .ok()
            .as_deref()
            != Some(id)
    {
        return Err(invalid());
    }
    if mode == "--hosted-private-tray" && hosted() && known == "private" {
        return tray::activation::assess(area, id);
    }
    if mode == "--hosted-toast-history"
        && hosted()
        && std::env::var("IFW_QA_TOAST_HISTORY").as_deref() == Ok("1")
        && std::env::var("GITHUB_REF").as_deref() == Ok("refs/heads/rewrite/rust")
        && std::env::var("GITHUB_REPOSITORY").as_deref() == Ok("VoltKraft/immich-folder-watch")
    {
        return toast::run(area, id, known.to_str().ok_or_else(invalid)?);
    }
    if mode == "--hosted-notification"
        && hosted()
        && known == "private"
        && std::env::var("IFW_QA_LATE_NOTIFICATION").as_deref() == Ok("1")
        && std::env::var("GITHUB_REF").as_deref() == Ok("refs/heads/rewrite/rust")
        && std::env::var("GITHUB_REPOSITORY").as_deref() == Ok("VoltKraft/immich-folder-watch")
    {
        return tray::notification_only(area, id);
    }
    if mode != "--isolated-session" && !(mode == "--github-hosted" && hosted()) {
        return Err(invalid());
    }
    let known = match known.to_str() {
        Some("private") => false,
        Some("hosted-startup") if hosted() => true,
        _ => return Err(invalid()),
    };
    let link = shortcuts::assess(area, id, known);
    if let Err(e) = &link {
        println!("shortcut.error={}", e.code().0);
    }
    // New thread, before allocating any HWND, COM object or hooks on that thread.
    let owned_id = id.to_owned();
    let empty =
        std::thread::spawn(move || tray::empty_desktop(&owned_id).map_err(|e| e.code().0)).join();
    match empty {
        Ok(Ok(())) => println!("empty.completed=true"),
        Ok(Err(code)) => println!("empty.error={code}"),
        Err(_) => println!("empty.thread_failed=true"),
    }
    let real = tray::assess(area, id);
    if let Err(e) = &real {
        println!("tray.error={}", e.code().0);
    }
    link.and(real)
}

#[cfg(windows)]
fn main() -> std::process::ExitCode {
    match run() {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("Probe HRESULT {}", error.code().0);
            std::process::ExitCode::FAILURE
        }
    }
}

#[cfg(not(windows))]
fn main() -> std::process::ExitCode {
    eprintln!("The native Windows service probe requires Windows.");
    std::process::ExitCode::FAILURE
}
