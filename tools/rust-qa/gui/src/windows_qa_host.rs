//! Identify the native Windows test host before using its synthetic profile.
use std::path::PathBuf;

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetComputerNameW(buffer: *mut u16, size: *mut u32) -> i32;
}
#[link(name = "advapi32")]
unsafe extern "system" {
    fn GetUserNameW(buffer: *mut u16, size: *mut u32) -> i32;
}

fn native_name(query: unsafe extern "system" fn(*mut u16, *mut u32) -> i32) -> Option<String> {
    let mut buffer = [0u16; 257];
    let mut size = buffer.len() as u32;
    // Both functions use character counts. GetUserNameW includes the trailing NUL.
    if unsafe { query(buffer.as_mut_ptr(), &mut size) } == 0 {
        return None;
    }
    let value = buffer.get(..size as usize)?;
    String::from_utf16(value.strip_suffix(&[0]).unwrap_or(value)).ok()
}

/// Return the designated parent directory and whether the caller is on the local QA guest.
pub fn fixture_temp() -> Option<(PathBuf, bool)> {
    let matches = |key, value| std::env::var(key).as_deref() == Ok(value);
    let local = matches("IFW_QA_LOCAL_WINDOWS", "1");
    let key = if local {
        if !cfg!(target_arch = "x86_64")
            || std::env::var_os("GITHUB_ACTIONS").is_some()
            || std::env::var_os("RUNNER_ENVIRONMENT").is_some()
            || !native_name(GetComputerNameW)?.eq_ignore_ascii_case("IFW-QA25")
            || !native_name(GetUserNameW)?.eq_ignore_ascii_case("ifw-test")
        {
            return None;
        }
        "IFW_QA_LOCAL_TEMP"
    } else {
        if !matches("GITHUB_ACTIONS", "true")
            || !matches("RUNNER_ENVIRONMENT", "github-hosted")
            || !matches("RUNNER_OS", "Windows")
        {
            return None;
        }
        "RUNNER_TEMP"
    };
    let directory = PathBuf::from(std::env::var_os(key)?);
    directory.is_absolute().then_some((directory, local))
}
