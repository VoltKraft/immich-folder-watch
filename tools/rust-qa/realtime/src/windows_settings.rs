//! Windows settings for the active connection of the current desktop user.
#![cfg(windows)]
#![allow(unsafe_code)]
#![deny(unsafe_op_in_unsafe_fn)]

use std::{
    io,
    net::{IpAddr, Ipv4Addr, Ipv6Addr},
    ptr, slice,
};
use windows_sys::Win32::{
    Foundation::{ERROR_SUCCESS, GlobalFree},
    NetworkManagement::IpHelper::{
        FreeMibTable, GetUnicastIpAddressTable, MIB_UNICASTIPADDRESS_TABLE,
    },
    Networking::{
        WinHttp::{WINHTTP_CURRENT_USER_IE_PROXY_CONFIG, WinHttpGetIEProxyConfigForCurrentUser},
        WinSock::{AF_INET, AF_INET6, AF_UNSPEC},
    },
};

pub struct Settings {
    pub automatic: bool,
    pub proxies: Option<String>,
    pub bypass: Option<String>,
}

struct Config(WINHTTP_CURRENT_USER_IE_PROXY_CONFIG);

impl Drop for Config {
    fn drop(&mut self) {
        for field in [
            self.0.lpszAutoConfigUrl,
            self.0.lpszProxy,
            self.0.lpszProxyBypass,
        ] {
            if !field.is_null() {
                // WinHTTP transfers each allocated string to this caller. No
                // pointer escapes Config and GlobalFree is its documented deallocator.
                unsafe { GlobalFree(field.cast()) };
            }
        }
    }
}

impl Config {
    fn string(&self, field: *const u16) -> io::Result<Option<String>> {
        if field.is_null() {
            return Ok(None);
        }
        // Only called on fields from a successful WinHTTP query. Each is a
        // NUL-terminated LPWSTR owned by self throughout this conversion.
        let mut len = 0;
        while len < 65_536 {
            if unsafe { *field.add(len) } == 0 {
                let units = unsafe { slice::from_raw_parts(field, len) };
                return String::from_utf16(units)
                    .map(Some)
                    .map_err(|_| io::ErrorKind::InvalidData.into());
            }
            len += 1;
        }
        Err(io::ErrorKind::InvalidData.into())
    }
}

pub fn current_user() -> io::Result<Settings> {
    let mut raw = WINHTTP_CURRENT_USER_IE_PROXY_CONFIG::default();
    // On success the properly aligned, zero-initialized out struct owns the
    // returned strings. WinHTTP does not retain a pointer to the local struct.
    if unsafe { WinHttpGetIEProxyConfigForCurrentUser(&mut raw) } == 0 {
        return Err(io::Error::last_os_error());
    }
    let config = Config(raw);
    Ok(Settings {
        automatic: config.0.fAutoDetect != 0
            || config
                .string(config.0.lpszAutoConfigUrl)?
                .is_some_and(|s| !s.is_empty()),
        proxies: config.string(config.0.lpszProxy)?,
        bypass: config.string(config.0.lpszProxyBypass)?,
    })
}

struct UnicastTable(*mut MIB_UNICASTIPADDRESS_TABLE);

impl Drop for UnicastTable {
    fn drop(&mut self) {
        // Construction occurs only after a successful IP Helper allocation.
        unsafe { FreeMibTable(self.0.cast()) };
    }
}

/// The Windows manual bypass token `<local>` includes interface unicast addresses.
pub fn has_local_address(needle: IpAddr) -> io::Result<bool> {
    let mut raw = ptr::null_mut();
    // IP Helper allocates the variable-length result and reports its row count.
    let error = unsafe { GetUnicastIpAddressTable(AF_UNSPEC, &mut raw) };
    if error != ERROR_SUCCESS {
        return Err(io::Error::from_raw_os_error(error as i32));
    }
    if raw.is_null() {
        return Err(io::ErrorKind::InvalidData.into());
    }
    let table = UnicastTable(raw);
    // The FFI table has a C flexible-array tail. Use the address of the raw
    // field without creating an array reference with the declared length one.
    let rows = unsafe {
        let start = ptr::addr_of!((*table.0).Table).cast();
        slice::from_raw_parts::<
            windows_sys::Win32::NetworkManagement::IpHelper::MIB_UNICASTIPADDRESS_ROW,
        >(start, (*table.0).NumEntries as usize)
    };
    Ok(rows.iter().any(|row| {
        // The common address-family field identifies the initialized union
        // member. The table remains owned until iteration is complete.
        let address = unsafe {
            match row.Address.si_family {
                AF_INET => IpAddr::V4(Ipv4Addr::from(
                    row.Address.Ipv4.sin_addr.S_un.S_addr.to_ne_bytes(),
                )),
                AF_INET6 if row.Address.Ipv6.Anonymous.sin6_scope_id == 0 => {
                    IpAddr::V6(Ipv6Addr::from(row.Address.Ipv6.sin6_addr.u.Byte))
                }
                _ => return false,
            }
        };
        needle == address
    }))
}
