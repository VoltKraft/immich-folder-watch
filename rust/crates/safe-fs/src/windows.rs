use super::staging::transaction_name;
use super::{Directory, EntryKind, FileIdentity, ObjectInfo, denied, internal_name};
use std::ffi::{OsStr, OsString, c_void};
use std::fs::{File, OpenOptions};
use std::io;
use std::mem::{size_of, size_of_val};
use std::os::windows::ffi::{OsStrExt, OsStringExt};
use std::os::windows::fs::OpenOptionsExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, RawHandle};
use std::path::{Component, Path, Prefix};
use std::ptr;

const READ_ATTRIBUTES: u32 = 0x80;
const WRITE_ATTRIBUTES: u32 = 0x100;
const SYNCHRONIZE: u32 = 0x100000;
const DIRECTORY_ACCESS: u32 = SYNCHRONIZE | READ_ATTRIBUTES | 1; // FILE_LIST_DIRECTORY
const SHARE_READ_WRITE: u32 = 3;
const SHARE_ALL: u32 = 7;
const OPEN_REPARSE_POINT: u32 = 0x200000;
const BACKUP_SEMANTICS: u32 = 0x02000000;
const FILE_SYNCHRONOUS_IO_NONALERT: u32 = 0x20;
const FILE_DIRECTORY_FILE: u32 = 1;
const FILE_NON_DIRECTORY_FILE: u32 = 0x40;
const FILE_OPEN: u32 = 1;
const FILE_CREATE: u32 = 2;
const DELETE: u32 = 0x10000;

#[repr(C)]
struct UnicodeString {
    length: u16,
    maximum_length: u16,
    buffer: *const u16,
}

#[repr(C)]
struct ObjectAttributes {
    length: u32,
    root: RawHandle,
    name: *const UnicodeString,
    attributes: u32,
    security_descriptor: *const c_void,
    security_qos: *const c_void,
}

#[derive(Default)]
#[repr(C)]
struct IoStatusBlock {
    status_or_pointer: usize,
    information: usize,
}

#[derive(Default)]
#[repr(C)]
struct HandleInformation {
    attributes: u32,
    created: [u32; 2],
    accessed: [u32; 2],
    written: [u32; 2],
    serial: u32,
    size_high: u32,
    size_low: u32,
    links: u32,
    index_high: u32,
    index_low: u32,
}

#[derive(Default)]
#[repr(C)]
struct FileIdInfo {
    volume: u64,
    identifier: [u8; 16],
}

#[repr(C)]
struct RenameInformation {
    flags: u32,
    root: RawHandle,
    name_bytes: u32,
    first_unit: u16,
}

const _: () = assert!(size_of::<ObjectAttributes>() == 48);
const _: () = assert!(size_of::<UnicodeString>() == 16);
const _: () = assert!(size_of::<IoStatusBlock>() == 16);
const _: () = assert!(size_of::<HandleInformation>() == 52);
const _: () = assert!(size_of::<FileIdInfo>() == 24);
const _: () = assert!(std::mem::offset_of!(RenameInformation, first_unit) == 20);

#[link(name = "ntdll")]
unsafe extern "system" {
    fn NtCreateFile(
        out: *mut RawHandle,
        access: u32,
        attributes: *const ObjectAttributes,
        status: *mut IoStatusBlock,
        allocation: *const i64,
        flags: u32,
        share: u32,
        disposition: u32,
        options: u32,
        ea: *const c_void,
        ea_size: u32,
    ) -> i32;
    fn RtlNtStatusToDosError(status: i32) -> u32;
    fn NtSetInformationFile(
        file: RawHandle,
        status: *mut IoStatusBlock,
        information: *const c_void,
        bytes: u32,
        class: u32,
    ) -> i32;
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetFileInformationByHandle(file: RawHandle, information: *mut HandleInformation) -> i32;
    fn GetFileInformationByHandleEx(
        file: RawHandle,
        class: i32,
        result: *mut c_void,
        bytes: u32,
    ) -> i32;
    fn GetFileType(file: RawHandle) -> u32;
    fn GetFinalPathNameByHandleW(file: RawHandle, name: *mut u16, capacity: u32, flags: u32)
    -> u32;
    fn GetVolumeInformationByHandleW(
        file: RawHandle,
        volume: *mut u16,
        volume_size: u32,
        serial: *mut u32,
        maximum_component_length: *mut u32,
        flags: *mut u32,
        fs_name: *mut u16,
        fs_name_size: u32,
    ) -> i32;
    fn SetFileInformationByHandle(
        file: RawHandle,
        class: i32,
        information: *const c_void,
        bytes: u32,
    ) -> i32;
}

#[link(name = "bcrypt")]
unsafe extern "system" {
    fn BCryptGenRandom(algorithm: RawHandle, buffer: *mut u8, bytes: u32, flags: u32) -> i32;
}

fn check_nt(status: i32) -> io::Result<()> {
    if status < 0 {
        // SAFETY: NTSTATUS translation has no pointer or lifetime preconditions.
        return Err(io::Error::from_raw_os_error(
            unsafe { RtlNtStatusToDosError(status) } as i32,
        ));
    }
    Ok(())
}

pub(super) fn open_root(path: &Path) -> io::Result<File> {
    let Some(Component::Prefix(prefix)) = path.components().next() else {
        return Err(denied("a Windows drive or UNC root is required"));
    };
    if !matches!(
        prefix.kind(),
        Prefix::Disk(_) | Prefix::VerbatimDisk(_) | Prefix::UNC(_, _) | Prefix::VerbatimUNC(_, _)
    ) {
        return Err(denied("device namespaces are outside the watch grant"));
    }
    let directory = OpenOptions::new()
        .access_mode(DIRECTORY_ACCESS)
        .share_mode(SHARE_READ_WRITE)
        .custom_flags(BACKUP_SEMANTICS | OPEN_REPARSE_POINT)
        .open(path)?;
    if path.file_name().is_some() {
        public_handle(directory)
    } else {
        Ok(directory)
    }
}

fn open_relative(
    parent: &File,
    name: &OsStr,
    access: u32,
    share: u32,
    disposition: u32,
    options: u32,
) -> io::Result<File> {
    let text: Vec<_> = name.encode_wide().collect();
    let length = u16::try_from(text.len().saturating_mul(2)).map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "child name exceeds the NT name limit",
        )
    })?;
    let name = UnicodeString {
        length,
        maximum_length: length,
        buffer: text.as_ptr(),
    };
    let attributes = ObjectAttributes {
        length: size_of::<ObjectAttributes>() as u32,
        root: parent.as_raw_handle(),
        name: &name,
        attributes: 0x40,
        security_descriptor: ptr::null(),
        security_qos: ptr::null(),
    };
    let mut raw = ptr::null_mut();
    let mut io_status = IoStatusBlock::default();
    // SAFETY: all input buffers, the counted UTF-16 name and parent are live.
    // SYNCHRONIZE and synchronous I/O keep the status block valid to completion.
    let status = unsafe {
        NtCreateFile(
            &mut raw,
            access | SYNCHRONIZE,
            &attributes,
            &mut io_status,
            ptr::null(),
            0x80,
            share,
            disposition,
            options | FILE_SYNCHRONOUS_IO_NONALERT | OPEN_REPARSE_POINT,
            ptr::null(),
            0,
        )
    };
    check_nt(status)?;
    // SAFETY: a successful synchronous NtCreateFile creates an owned handle.
    Ok(unsafe { File::from_raw_handle(raw) })
}

pub(super) fn open_directory(parent: &File, name: &OsStr) -> io::Result<File> {
    open_relative(
        parent,
        name,
        DIRECTORY_ACCESS,
        SHARE_READ_WRITE,
        FILE_OPEN,
        FILE_DIRECTORY_FILE,
    )
    .and_then(public_handle)
}

pub(super) fn open_file(parent: &File, name: &OsStr, writable_times: bool) -> io::Result<File> {
    let access = 0x80000000 | if writable_times { WRITE_ATTRIBUTES } else { 0 };
    open_relative(
        parent,
        name,
        access,
        SHARE_ALL,
        FILE_OPEN,
        FILE_NON_DIRECTORY_FILE,
    )
    .and_then(public_handle)
}

pub(super) fn entry_info(parent: &File, name: &OsStr) -> io::Result<ObjectInfo> {
    info(
        &open_relative(parent, name, READ_ATTRIBUTES, SHARE_ALL, FILE_OPEN, 0)
            .and_then(public_handle)?,
    )
}

fn public_handle(file: File) -> io::Result<File> {
    // NTFS short names can alias a reserved long name. Query the normalized
    // name of the selected handle solely to reject such aliases. No subsequent
    // operation resolves the returned path. Denial or unavailable information
    // must keep the caller from using the entry.
    let mut name = vec![0u16; 256];
    loop {
        // SAFETY: the buffer is live with the stated UTF-16 capacity. Flags
        // request FILE_NAME_NORMALIZED and VOLUME_NAME_NONE.
        let length = unsafe {
            GetFinalPathNameByHandleW(
                file.as_raw_handle(),
                name.as_mut_ptr(),
                name.len() as u32,
                4,
            )
        } as usize;
        if length == 0 {
            return Err(io::Error::last_os_error());
        }
        if length < name.len() {
            if internal_name(&OsString::from_wide(&name[..length])) {
                return Err(denied(
                    "internal transaction entries are outside the media grant",
                ));
            }
            return Ok(file);
        }
        if length == name.len() || length > 32768 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "invalid normalized entry name length",
            ));
        }
        name.resize(length, 0);
    }
}

fn identity(file: &File, basic: &HandleInformation) -> io::Result<FileIdentity> {
    let mut id = FileIdInfo::default();
    // SAFETY: correctly sized, aligned output for FileIdInfo; file stays open.
    if unsafe {
        GetFileInformationByHandleEx(
            file.as_raw_handle(),
            18,
            (&mut id as *mut FileIdInfo).cast(),
            size_of::<FileIdInfo>() as u32,
        )
    } != 0
    {
        return Ok(FileIdentity {
            volume: id.volume,
            file: u128::from_le_bytes(id.identifier),
        });
    }
    let mut fs_name = [0u16; 32];
    // SAFETY: unused outputs may be null. fs_name has the supplied UTF-16 capacity.
    if unsafe {
        GetVolumeInformationByHandleW(
            file.as_raw_handle(),
            ptr::null_mut(),
            0,
            ptr::null_mut(),
            ptr::null_mut(),
            ptr::null_mut(),
            fs_name.as_mut_ptr(),
            fs_name.len() as u32,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    let length = fs_name
        .iter()
        .position(|&c| c == 0)
        .ok_or_else(|| io::Error::other("invalid filesystem name"))?;
    let fs = String::from_utf16_lossy(&fs_name[..length]);
    if !["FAT", "FAT32", "exFAT"]
        .iter()
        .any(|name| name.eq_ignore_ascii_case(&fs))
    {
        return Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "filesystem lacks a supported stable file identifier",
        ));
    }
    Ok(FileIdentity {
        volume: basic.serial.into(),
        file: (u128::from(basic.index_high) << 32) | u128::from(basic.index_low),
    })
}

pub(super) fn info(file: &File) -> io::Result<ObjectInfo> {
    let mut basic = HandleInformation::default();
    // SAFETY: output is a live BY_HANDLE_FILE_INFORMATION with the documented layout.
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut basic) } == 0 {
        return Err(io::Error::last_os_error());
    }
    if basic.attributes & 0x400 != 0 {
        return Err(denied("reparse points are outside the watch grant"));
    }
    // SAFETY: GetFileType borrows the live handle without changing ownership.
    let disk = unsafe { GetFileType(file.as_raw_handle()) } == 1;
    let kind = if !disk {
        EntryKind::Other
    } else if basic.attributes & 0x10 != 0 {
        EntryKind::Directory
    } else {
        EntryKind::File
    };
    Ok(ObjectInfo {
        kind,
        identity: identity(file, &basic)?,
        links: basic.links.into(),
    })
}

fn dir_records(
    mut bytes: &[u8],
    visit: &mut impl FnMut(OsString) -> io::Result<()>,
) -> io::Result<()> {
    // FILE_ID_BOTH_DIR_INFO on both supported 64-bit ABIs. Read individual
    // fields from bytes to avoid alignment assumptions for variable-length names.
    const NAME_OFFSET: usize = 104;
    let malformed = || io::Error::new(io::ErrorKind::InvalidData, "invalid directory record");
    loop {
        let header = bytes.get(..NAME_OFFSET).ok_or_else(malformed)?;
        let next = u32::from_le_bytes(header[0..4].try_into().unwrap()) as usize;
        let length = u32::from_le_bytes(header[60..64].try_into().unwrap()) as usize;
        if length == 0
            || !length.is_multiple_of(2)
            || (next != 0 && (!next.is_multiple_of(8) || next < NAME_OFFSET + length))
        {
            return Err(malformed());
        }
        let name = bytes
            .get(NAME_OFFSET..NAME_OFFSET + length)
            .ok_or_else(malformed)?;
        let wide: Vec<_> = name
            .chunks_exact(2)
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect();
        visit(OsString::from_wide(&wide))?;
        if next == 0 {
            return Ok(());
        }
        bytes = bytes.get(next..).ok_or_else(malformed)?;
    }
}

pub(super) fn enumerate(
    file: &File,
    mut visit: impl FnMut(OsString) -> io::Result<()>,
) -> io::Result<()> {
    let mut buffer = vec![0u64; 8192]; // 64 KiB, naturally aligned for LARGE_INTEGER fields.
    let capacity = size_of_val(buffer.as_slice());
    let mut class = 11; // FileIdBothDirectoryRestartInfo
    loop {
        // SAFETY: writable, aligned output has exactly capacity bytes. The caller
        // serializes this handle's directory cursor and holds the File throughout.
        if unsafe {
            GetFileInformationByHandleEx(
                file.as_raw_handle(),
                class,
                buffer.as_mut_ptr().cast(),
                capacity as u32,
            )
        } == 0
        {
            let err = io::Error::last_os_error();
            return if err.raw_os_error() == Some(18) {
                Ok(())
            } else {
                Err(err)
            }; // ERROR_NO_MORE_FILES
        }
        // SAFETY: the vector is initialized and every u64 bit pattern is valid.
        let bytes = unsafe { std::slice::from_raw_parts(buffer.as_ptr().cast::<u8>(), capacity) };
        dir_records(bytes, &mut visit)?;
        class = 10; // FileIdBothDirectoryInfo continues the cursor.
    }
}

pub(super) fn random_bytes() -> io::Result<[u8; 16]> {
    let mut bytes = [0; 16];
    // SAFETY: the output array has 16 writable bytes. The system-preferred
    // RNG flag allows a null algorithm provider.
    check_nt(unsafe {
        BCryptGenRandom(ptr::null_mut(), bytes.as_mut_ptr(), bytes.len() as u32, 2)
    })?;
    Ok(bytes)
}

fn mark_delete(file: &File) -> io::Result<()> {
    let delete: u8 = 1; // FILE_DISPOSITION_INFO.DeleteFile is a BOOLEAN.
    // SAFETY: FileDispositionInfo takes a one-byte input and a live handle.
    if unsafe {
        SetFileInformationByHandle(file.as_raw_handle(), 4, (&delete as *const u8).cast(), 1)
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn rename_handle(file: &File, destination: &File, name: &OsStr) -> io::Result<()> {
    let text: Vec<_> = name.encode_wide().collect();
    let name_bytes = u16::try_from(text.len().saturating_mul(2)).map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "destination name exceeds the NT name limit",
        )
    })?;
    let offset = std::mem::offset_of!(RenameInformation, first_unit);
    let size = (offset + usize::from(name_bytes)).max(size_of::<RenameInformation>());
    let mut record = vec![0usize; size.div_ceil(size_of::<usize>())];
    let raw = record.as_mut_ptr().cast::<u8>();
    let header = raw.cast::<RenameInformation>();
    let mut io_status = IoStatusBlock::default();
    // SAFETY: record is pointer-aligned and large enough for the native header
    // and the counted UTF-16 flexible array. The zero flags forbid replacement.
    // Target and source handles outlive this synchronous operation.
    let status = unsafe {
        (&raw mut (*header).root).write(destination.as_raw_handle());
        (&raw mut (*header).name_bytes).write(u32::from(name_bytes));
        ptr::copy_nonoverlapping(text.as_ptr(), raw.add(offset).cast::<u16>(), text.len());
        NtSetInformationFile(
            file.as_raw_handle(),
            &mut io_status,
            raw.cast(),
            size as u32,
            10,
        )
    };
    check_nt(status)
}

#[derive(Debug)]
pub(super) struct Transaction {
    directory: File,
}

impl Transaction {
    pub(super) fn new(parent: &Directory) -> io::Result<Self> {
        let name = transaction_name()?;
        let directory = open_relative(
            &parent.0.file,
            &name,
            DIRECTORY_ACCESS | DELETE,
            SHARE_READ_WRITE,
            FILE_CREATE,
            FILE_DIRECTORY_FILE,
        )?;
        info(&directory)?.require(EntryKind::Directory)?;
        Ok(Self { directory })
    }

    pub(super) fn create_payload(&self) -> io::Result<File> {
        // An exclusive handle prevents competing opens until publication or cancellation.
        let file = open_relative(
            &self.directory,
            OsStr::new("payload"),
            0xc0000000 | DELETE,
            0,
            FILE_CREATE,
            FILE_NON_DIRECTORY_FILE,
        )?;
        info(&file)?.require(EntryKind::File)?;
        Ok(file)
    }

    pub(super) fn rename_payload(
        &self,
        file: &File,
        destination: &File,
        name: &OsStr,
    ) -> io::Result<()> {
        rename_handle(file, destination, name)
    }

    pub(super) fn remove_payload(&self, file: &File) -> io::Result<()> {
        mark_delete(file)
    }

    pub(super) fn remove_directory(self) -> io::Result<()> {
        mark_delete(&self.directory)
    }
}
