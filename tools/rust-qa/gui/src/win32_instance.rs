//! Current-account mutexes and local byte pipes for the native activation fixtures.
use std::ffi::c_void;
use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::os::windows::fs::OpenOptionsExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle, RawHandle};
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

struct Descriptor(*mut c_void);
impl Drop for Descriptor {
    fn drop(&mut self) {
        unsafe { LocalFree(self.0) };
    }
}

impl Descriptor {
    fn for_owner(sid: &str) -> io::Result<Self> {
        if !valid_sid(sid) {
            return Err(io::ErrorKind::InvalidInput.into());
        }
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

pub fn valid_sid(owner: &str) -> bool {
    let Some(rest) = owner.strip_prefix("S-1-") else {
        return false;
    };
    let parts: Vec<_> = rest.split('-').collect();
    (2..=16).contains(&parts.len())
        && parts.iter().all(|part| {
            !part.is_empty()
                && part.len() <= 10
                && part.bytes().all(|b| b.is_ascii_digit())
                && part.parse::<u32>().is_ok()
        })
}

pub fn mutex(name: &str, sid: Option<&str>) -> io::Result<(OwnedHandle, bool)> {
    let descriptor = sid.map(Descriptor::for_owner).transpose()?;
    let attributes = descriptor.as_ref().map(Descriptor::attributes);
    let name = wide(name);
    // First creation elects the primary. The mutex exists until the last handle closes.
    let handle = unsafe {
        CreateMutexW(
            attributes.as_ref().map_or(null(), std::ptr::from_ref),
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

pub fn inbound(name: &str, sid: &str) -> io::Result<File> {
    let descriptor = Descriptor::for_owner(sid)?;
    let name = wide(name);
    // First and only instance, inbound bytes, local clients only, current-account DACL.
    let handle = unsafe {
        CreateNamedPipeW(
            name.as_ptr(),
            0x80001,
            8,
            1,
            0,
            64,
            5000,
            &descriptor.attributes(),
        )
    };
    if handle as isize == -1 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_handle(handle) })
}

pub fn accept(pipe: &File) -> io::Result<()> {
    if unsafe { ConnectNamedPipe(pipe.as_raw_handle(), null_mut()) } != 0 {
        return Ok(());
    }
    let error = io::Error::last_os_error();
    // A client connected after pipe creation and before ConnectNamedPipe.
    if error.raw_os_error() == Some(535) {
        Ok(())
    } else {
        Err(error)
    }
}

pub fn peer_pid(pipe: &File, server: bool) -> io::Result<u32> {
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
    Ok(actual)
}

pub fn client(name: &str) -> io::Result<File> {
    // SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION.
    OpenOptions::new()
        .write(true)
        .security_qos_flags(0x110000)
        .open(name)
}

pub fn connect(name: &str, timeout: Duration) -> io::Result<File> {
    let deadline = Instant::now() + timeout;
    loop {
        match client(name) {
            Ok(pipe) => return Ok(pipe),
            Err(e) if matches!(e.raw_os_error(), Some(2 | 231)) && Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(10))
            }
            Err(e) => return Err(e),
        }
    }
}

pub fn send(mut pipe: &File, expected: u32, signal: &[u8]) -> io::Result<()> {
    if peer_pid(pipe, true)? != expected {
        return Err(io::Error::other("unexpected local activation peer"));
    }
    pipe.write_all(signal)
}
