use std::ffi::{OsStr, OsString};
use std::fs::{self, OpenOptions};
use std::os::windows::ffi::OsStringExt;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};
use windows::Win32::Foundation::HWND;
use windows::Win32::System::Com::*;
use windows::Win32::UI::Shell::*;
use windows::core::{GUID, Interface, PCWSTR, Result, w};

use crate::{invalid, wide};

struct Apartment;
impl Drop for Apartment {
    fn drop(&mut self) {
        // This guard only exists after successful initialization on this thread.
        unsafe { CoUninitialize() }
    }
}

struct OwnedLink {
    path: Option<PathBuf>,
    contents: Vec<u8>,
}
impl OwnedLink {
    fn disable(&mut self) -> Result<()> {
        if let Some(path) = &self.path {
            if fs::read(path)? != self.contents {
                return Err(invalid());
            }
            fs::remove_file(path)?;
            self.path.take();
        }
        Ok(())
    }
}
impl Drop for OwnedLink {
    fn drop(&mut self) {
        let _ = self.disable();
    }
}

pub(super) fn known_folder(id: &GUID) -> Result<PathBuf> {
    // The operating system owns the choice of per-user directory. The returned
    // allocation belongs to the caller and is released with its matching allocator.
    unsafe {
        let path = SHGetKnownFolderPath(id, KF_FLAG_DEFAULT, None)?;
        let owned = OsString::from_wide(path.as_wide());
        CoTaskMemFree(Some(path.as_ptr().cast()));
        Ok(owned.into())
    }
}

pub(super) fn read_string(buffer: &[u16]) -> OsString {
    OsString::from_wide(&buffer[..buffer.iter().position(|&v| v == 0).unwrap_or(buffer.len())])
}

fn same_file(path: &OsStr, expected: &Path) -> bool {
    match (fs::canonicalize(path), fs::canonicalize(expected)) {
        (Ok(a), Ok(b)) => a == b,
        _ => false,
    }
}

fn roundtrip(area: &Path, dir: &Path, id: &str, label: &str, executable: &Path) -> Result<()> {
    let target = wide(executable.as_os_str());
    let parent = executable.parent().ok_or_else(invalid)?;
    let working = wide(parent.as_os_str());
    let path = dir.join(format!("IFW-RW02-{id}.lnk"));
    let filename = wide(path.as_os_str());
    // Reserve a new name atomically. On collision, even the cleanup guard is
    // never constructed. The parent can recover a probe-owned file after timeout.
    drop(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)?,
    );
    let mut owned = OwnedLink {
        path: Some(path.clone()),
        contents: Vec::new(),
    };
    fs::write(
        area.join(format!("{label}.owned")),
        path.to_str().ok_or_else(invalid)?,
    )?;
    // COM references drop before apartment teardown. All UTF-16 inputs are
    // NUL-terminated and outlive the synchronous calls that consume them.
    unsafe {
        let link: IShellLinkW = CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER)?;
        link.SetPath(PCWSTR(target.as_ptr()))?;
        link.SetArguments(w!("--autostart"))?;
        link.SetWorkingDirectory(PCWSTR(working.as_ptr()))?;
        link.SetDescription(w!("Immich Folder Watch synthetic startup"))?;
        link.SetIconLocation(PCWSTR(target.as_ptr()), 0)?;
        link.cast::<IPersistFile>()?
            .Save(PCWSTR(filename.as_ptr()), true)?;
        drop(link);
        // Recovery may remove only our original bytes or the empty reservation.
        // This private copy never leaves the temporary fixture directory.
        owned.contents = fs::read(&path)?;
        fs::write(area.join(format!("{label}.saved")), &owned.contents)?;

        let reopened: IShellLinkW = CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER)?;
        reopened
            .cast::<IPersistFile>()?
            .Load(PCWSTR(filename.as_ptr()), STGM_READ)?;
        reopened.Resolve(
            HWND::default(),
            (SLR_NO_UI | SLR_NOSEARCH | SLR_NOTRACK | SLR_NOUPDATE).0 as u32,
        )?;
        let mut buf = vec![0u16; 32768];
        reopened.GetPath(&mut buf, std::ptr::null_mut(), SLGP_RAWPATH.0 as u32)?;
        let target_ok = same_file(&read_string(&buf), executable);
        reopened.GetArguments(&mut buf)?;
        let arg_ok = read_string(&buf) == "--autostart";
        reopened.GetWorkingDirectory(&mut buf)?;
        let working_ok = same_file(&read_string(&buf), parent);
        reopened.GetDescription(&mut buf)?;
        let desc_ok = read_string(&buf) == "Immich Folder Watch synthetic startup";
        let mut index = -1;
        reopened.GetIconLocation(&mut buf, &mut index)?;
        let icon_ok = index == 0 && same_file(&read_string(&buf), executable);
        println!(
            "{label}.target={target_ok}\n{label}.arguments={arg_ok}\n{label}.working_directory={working_ok}\n{label}.description={desc_ok}\n{label}.icon={icon_ok}"
        );
        if !(target_ok && arg_ok && working_ok && desc_ok && icon_ok) {
            return Err(invalid());
        }
    }
    // An independent Windows Script Host reader checks the same shortcut
    // before the native service disables it. Never execute the shortcut.
    fs::write(area.join(format!("{label}.ready")), [])?;
    let until = Instant::now() + Duration::from_secs(75);
    while !area.join(format!("{label}.observed")).is_file() {
        if Instant::now() >= until {
            return Err(invalid());
        }
        std::thread::sleep(Duration::from_millis(40));
    }
    owned.disable()?;
    fs::remove_file(area.join(format!("{label}.owned")))?;
    let disabled = !path.try_exists()?;
    println!("{label}.disabled={disabled}");
    if disabled { Ok(()) } else { Err(invalid()) }
}

pub(super) fn assess(area: &Path, id: &str, known: bool) -> Result<()> {
    // The assessing thread owns its STA and all shell-link interfaces.
    unsafe {
        CoInitializeEx(None, COINIT_APARTMENTTHREADED).ok()?;
    }
    let _apartment = Apartment;
    let exe = std::env::current_exe()?;
    let private = area.join("Synthetic Startup");
    fs::create_dir(&private)?;
    roundtrip(area, &private, id, "private", &exe)?;
    if known {
        roundtrip(area, &known_folder(&FOLDERID_Startup)?, id, "startup", &exe)?;
    }
    Ok(())
}
