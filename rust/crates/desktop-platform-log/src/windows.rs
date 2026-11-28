use crate::{Level, Record};
use std::ffi::c_void;
use std::io;
use std::ptr::{null, null_mut};

type Handle = *mut c_void;
const HKLM: Handle = -2_147_483_646isize as Handle;

#[link(name = "advapi32")]
unsafe extern "system" {
    fn RegOpenKeyExW(
        root: Handle,
        path: *const u16,
        options: u32,
        access: u32,
        key: *mut Handle,
    ) -> i32;
    fn RegCloseKey(key: Handle) -> i32;
    fn RegisterEventSourceW(server: *const u16, source: *const u16) -> Handle;
    fn DeregisterEventSource(source: Handle) -> i32;
    fn ReportEventW(
        source: Handle,
        kind: u16,
        category: u16,
        id: u32,
        user: *const c_void,
        count: u16,
        size: u32,
        strings: *const *const u16,
        data: *const c_void,
    ) -> i32;
}

fn wide(value: &str) -> io::Result<Vec<u16>> {
    if value.contains('\0') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "embedded NUL in event log input",
        ));
    }
    Ok(value.encode_utf16().chain(Some(0)).collect())
}

/// A previously registered local classic Event Log source, opened without elevation.
pub struct EventLog(Handle);

impl EventLog {
    pub fn open(log: &str, source: &str) -> io::Result<Self> {
        for name in [log, source] {
            if name.is_empty() || name.contains(['\\', '/', '\0']) {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "invalid event log or source name",
                ));
            }
        }
        // RegisterEventSourceW otherwise silently redirects an unknown source to Application.
        let path = wide(&format!(
            r"SYSTEM\CurrentControlSet\Services\EventLog\{log}\{source}"
        ))?;
        let source = wide(source)?;
        let mut key = null_mut();
        // SAFETY: path is terminated and key is an initialized out-parameter. QUERY_VALUE only.
        let result = unsafe { RegOpenKeyExW(HKLM, path.as_ptr(), 0, 1, &mut key) };
        if result != 0 {
            return Err(io::Error::from_raw_os_error(result));
        }
        // SAFETY: key was opened above; the source string remains live for the API call.
        let handle = unsafe {
            let handle = RegisterEventSourceW(null(), source.as_ptr());
            let error = handle.is_null().then(io::Error::last_os_error);
            RegCloseKey(key);
            if let Some(error) = error {
                return Err(error);
            }
            handle
        };
        Ok(Self(handle))
    }

    /// Use a message-table event ID whose template contains a single insertion string.
    pub fn write(&self, id: u32, record: &Record<'_>) -> io::Result<()> {
        let kind = match record.level {
            Level::Critical | Level::Error => 1,
            Level::Warning => 2,
            Level::Information | Level::Debug | Level::Trace => 4,
        };
        let text = wide(&format!(
            "Category: {}\r\nEventId: {}\r\n\r\n{}\r\n",
            record.category, record.event_id, record.message
        ))?;
        let argument = text.as_ptr();
        // SAFETY: the owned source is open and the one UTF-16 insertion is live until return.
        if unsafe { ReportEventW(self.0, kind, 0, id, null(), 1, 0, &argument, null()) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }
}

impl Drop for EventLog {
    fn drop(&mut self) {
        // SAFETY: this handle comes solely from RegisterEventSourceW and is closed once.
        unsafe { DeregisterEventSource(self.0) };
    }
}
