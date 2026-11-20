use super::{SIGNAL, TIMEOUT, announce};
use std::ffi::c_void;
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::windows::fs::OpenOptionsExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle, RawHandle};
use std::path::Path;
use std::ptr::{null, null_mut};
use std::time::{Duration, Instant};

#[repr(C)]
struct SecurityAttributes {
    size: u32,
    descriptor: *mut c_void,
    inherit: i32,
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn CreateMutexW(
        attributes: *const SecurityAttributes,
        owned: i32,
        name: *const u16,
    ) -> RawHandle;
    fn GetLastError() -> u32;
    fn CreateNamedPipeW(
        name: *const u16,
        access: u32,
        mode: u32,
        instances: u32,
        out_size: u32,
        in_size: u32,
        timeout: u32,
        attributes: *const SecurityAttributes,
    ) -> RawHandle;
    fn ConnectNamedPipe(pipe: RawHandle, overlapped: *mut c_void) -> i32;
    fn GetNamedPipeClientProcessId(pipe: RawHandle, pid: *mut u32) -> i32;
    fn GetNamedPipeServerProcessId(pipe: RawHandle, pid: *mut u32) -> i32;
    fn LocalFree(memory: *mut c_void) -> *mut c_void;
}

#[link(name = "advapi32")]
unsafe extern "system" {
    fn ConvertStringSecurityDescriptorToSecurityDescriptorW(
        text: *const u16,
        revision: u32,
        descriptor: *mut *mut c_void,
        bytes: *mut u32,
    ) -> i32;
}

fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(Some(0)).collect()
}

pub fn check_environment(_: &Path, owner: &str) -> io::Result<()> {
    for (key, value) in [
        ("RUNNER_ENVIRONMENT", "github-hosted"),
        ("GITHUB_ACTIONS", "true"),
        ("GITHUB_REPOSITORY", "VoltKraft/immich-folder-watch"),
        ("GITHUB_REF", "refs/heads/rewrite/rust"),
    ] {
        if std::env::var(key).as_deref() != Ok(value) {
            return Err(io::Error::other(
                "the legacy IPC names require the rewrite branch's disposable Windows runner",
            ));
        }
    }
    let components: Vec<_> = owner
        .strip_prefix("S-1-")
        .unwrap_or("")
        .split('-')
        .collect();
    if !(2..=16).contains(&components.len())
        || components.iter().any(|value| {
            value.is_empty()
                || value.len() > 10
                || !value.bytes().all(|c| c.is_ascii_digit())
                || value.parse::<u32>().is_err()
        })
    {
        return Err(io::Error::other(
            "invalid account SID from the development oracle",
        ));
    }
    Ok(())
}

struct Descriptor(*mut c_void);
impl Drop for Descriptor {
    fn drop(&mut self) {
        unsafe { LocalFree(self.0) };
    }
}

impl Descriptor {
    fn for_owner(sid: &str) -> io::Result<Self> {
        let acl = wide(&format!("D:P(A;;GA;;;{sid})"));
        let mut descriptor = null_mut();
        if unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                acl.as_ptr(),
                1,
                &mut descriptor,
                null_mut(),
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(Self(descriptor))
    }

    fn attributes(&self) -> SecurityAttributes {
        SecurityAttributes {
            size: size_of::<SecurityAttributes>() as u32,
            descriptor: self.0,
            inherit: 0,
        }
    }
}

fn mutex(sid: &str, attributes: Option<&SecurityAttributes>) -> io::Result<(OwnedHandle, bool)> {
    let name = wide(&format!(r"Local\ImmichFolderWatch-{sid}"));
    // The shipping coordinator elects by first creation. Existence is maintained by this handle.
    let handle = unsafe {
        CreateMutexW(
            attributes.map_or(null(), std::ptr::from_ref),
            0,
            name.as_ptr(),
        )
    };
    let last_error = unsafe { GetLastError() };
    if handle.is_null() {
        return Err(io::Error::from_raw_os_error(last_error as i32));
    }
    Ok((
        unsafe { OwnedHandle::from_raw_handle(handle) },
        last_error != 183,
    ))
}

fn pipe_name(sid: &str) -> String {
    format!(r"\\.\pipe\ifw-{sid}")
}

fn check_peer(pipe: &File, server: bool, expected: u32) -> io::Result<()> {
    let mut actual = 0;
    let ok = unsafe {
        if server {
            GetNamedPipeServerProcessId(pipe.as_raw_handle(), &mut actual)
        } else {
            GetNamedPipeClientProcessId(pipe.as_raw_handle(), &mut actual)
        }
    };
    if ok == 0 {
        return Err(io::Error::last_os_error());
    }
    if actual != expected {
        return Err(io::Error::other("unexpected local activation peer"));
    }
    Ok(())
}

pub fn signal(_: &Path, sid: &str, peer: u32) -> io::Result<()> {
    let (_mutex, created) = mutex(sid, None)?;
    if created {
        return Err(io::Error::other("expected an existing legacy mutex"));
    }
    let name = pipe_name(sid);
    let deadline = Instant::now() + TIMEOUT;
    let mut pipe = loop {
        // SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION.
        match OpenOptions::new()
            .write(true)
            .security_qos_flags(0x110000)
            .open(&name)
        {
            Ok(file) => break file,
            Err(error)
                if matches!(error.raw_os_error(), Some(2 | 231)) && Instant::now() < deadline =>
            {
                std::thread::sleep(Duration::from_millis(10));
            }
            Err(error) => return Err(error),
        }
    };
    check_peer(&pipe, true, peer)?;
    pipe.write_all(SIGNAL)?;
    drop(pipe);
    announce("SECONDARY_SIGNALLED")
}

pub fn listen(_: &Path, sid: &str, peer: u32) -> io::Result<()> {
    let descriptor = Descriptor::for_owner(sid)?;
    let attributes = descriptor.attributes();
    let (_mutex, created) = mutex(sid, Some(&attributes))?;
    if !created {
        return Err(io::Error::other("an existing owner holds the legacy mutex"));
    }
    let name = wide(&pipe_name(sid));
    // One local inbound byte pipe with FILE_FLAG_FIRST_PIPE_INSTANCE and PIPE_REJECT_REMOTE_CLIENTS.
    let handle =
        unsafe { CreateNamedPipeW(name.as_ptr(), 0x80001, 8, 1, 0, 64, 5000, &attributes) };
    if handle as isize == -1 {
        return Err(io::Error::last_os_error());
    }
    let pipe = unsafe { File::from_raw_handle(handle) };
    announce("PRIMARY_READY")?;
    // The harness also enforces an end-to-end process deadline on ConnectNamedPipe and the read.
    if unsafe { ConnectNamedPipe(handle, null_mut()) } == 0 {
        let error = io::Error::last_os_error();
        if error.raw_os_error() != Some(535) {
            return Err(error);
        }
    }
    check_peer(&pipe, false, peer)?;
    let mut bytes = Vec::new();
    let result = pipe.take(65).read_to_end(&mut bytes);
    if let Err(error) = result
        && error.kind() != io::ErrorKind::BrokenPipe
    {
        return Err(error);
    }
    if bytes != SIGNAL {
        return Err(io::ErrorKind::InvalidData.into());
    }
    announce("SHOW_GUI")
}
