//! Native admission probe for the installed MSI on an explicitly marked disposable Windows VM.
use std::ffi::c_void;
use std::fs;
use std::io::{self, BufRead, Read, Write};
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle, RawHandle};
use std::time::Duration;

#[allow(dead_code)]
#[path = "../../gui/src/win32_instance.rs"]
mod local;

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetCurrentProcess() -> RawHandle;
    fn ProcessIdToSessionId(pid: u32, session: *mut u32) -> i32;
    fn LocalFree(memory: *mut c_void) -> *mut c_void;
}

#[link(name = "advapi32")]
unsafe extern "system" {
    fn OpenProcessToken(process: RawHandle, access: u32, token: *mut RawHandle) -> i32;
    fn GetTokenInformation(
        token: RawHandle,
        class: u32,
        data: *mut c_void,
        size: u32,
        used: *mut u32,
    ) -> i32;
    fn ConvertSidToStringSidW(sid: *mut c_void, text: *mut *mut u16) -> i32;
}

const MARKER: &str = r"C:\Program Files\IFW-QA-CrossSession\marker.txt";

fn identity() -> io::Result<(String, u32)> {
    let marker = fs::read_to_string(MARKER)
        .map_err(|_| io::Error::other("expected disposable MSI test VM marker"))?;
    let mut token = std::ptr::null_mut();
    let mut session = 0;
    if unsafe { OpenProcessToken(GetCurrentProcess(), 8, &mut token) } == 0 {
        return Err(io::Error::last_os_error());
    }
    let token = unsafe { OwnedHandle::from_raw_handle(token) };
    if unsafe { ProcessIdToSessionId(std::process::id(), &mut session) } == 0 || session == 0 {
        return Err(io::Error::other(
            "expected an interactive standard-user session",
        ));
    }
    let mut used = 0;
    for (class, expected) in [(18, 1), (20, 0)] {
        // Default elevation type and TokenIsElevated=false.
        let mut value = u32::MAX;
        if unsafe {
            GetTokenInformation(
                token.as_raw_handle(),
                class,
                (&raw mut value).cast(),
                4,
                &mut used,
            )
        } == 0
            || used != 4
            || value != expected
        {
            return Err(io::Error::other(
                "expected an ordinary account with a non-elevated token",
            ));
        }
    }
    // TOKEN_USER begins with an aligned SID pointer. The fixed buffer covers SECURITY_MAX_SID_SIZE.
    let mut user = [0usize; 128];
    if unsafe {
        GetTokenInformation(
            token.as_raw_handle(),
            1,
            user.as_mut_ptr().cast(),
            size_of_val(&user) as u32,
            &mut used,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    let mut text = std::ptr::null_mut();
    if unsafe { ConvertSidToStringSidW(user[0] as *mut c_void, &mut text) } == 0 {
        return Err(io::Error::last_os_error());
    }
    // Windows constructs this NUL-terminated SID string for the process's own token.
    let mut length = 0;
    while unsafe { *text.add(length) } != 0 {
        length += 1;
    }
    let sid = String::from_utf16(unsafe { std::slice::from_raw_parts(text, length) });
    unsafe { LocalFree(text.cast()) };
    let sid = sid.map_err(io::Error::other)?;
    if !local::valid_sid(&sid)
        || marker != format!("IFW disposable installed MSI session test\n{sid}\n")
    {
        return Err(io::Error::other(
            "the test VM marker must name this specific standard account",
        ));
    }
    Ok((sid, session))
}

fn emit(event: &str) -> io::Result<()> {
    println!("{event}");
    io::stdout().flush()
}

fn main() -> io::Result<()> {
    if std::env::args_os().len() != 1 {
        return Err(io::ErrorKind::InvalidInput.into());
    }
    let (sid, session) = identity()?;
    let (_owner, created) = local::mutex(&format!(r"Local\ImmichFolderWatch-{sid}"), Some(&sid))?;
    emit(&format!(
        "SESSION_MUTEX session={session} created={created}"
    ))?;
    if !created {
        return Err(io::Error::other("existing session primary"));
    }
    let name = format!(r"\\.\pipe\ifw-{sid}");
    let server = match local::inbound(&name, &sid) {
        Ok(server) => server,
        Err(err) => {
            emit(&format!("PIPE_REFUSED code={:?}", err.raw_os_error()))?;
            // Independently identify the occupied pipe. Closing this connection sends no activation command.
            let probe = local::connect(&name, Duration::from_secs(2))?;
            emit(&format!(
                "EXISTING_PIPE_SERVER pid={}",
                local::peer_pid(&probe, true)?
            ))?;
            return Ok(());
        }
    };
    let _listener = std::thread::spawn(move || -> io::Result<()> {
        local::accept(&server)?;
        let pid = local::peer_pid(&server, false)?;
        let mut bytes = Vec::new();
        server.take(65).read_to_end(&mut bytes)?;
        if bytes != b"SHOW_GUI" {
            return Err(io::ErrorKind::InvalidData.into());
        }
        emit(&format!("SHOW_GUI pid={pid}"))
    });
    emit("RUST_PRIMARY")?;
    if io::stdin().lock().lines().next().transpose()?.as_deref() != Some("RELEASE") {
        return Err(io::Error::other("expected an orderly release"));
    }
    emit("RUST_RELEASED")
}
