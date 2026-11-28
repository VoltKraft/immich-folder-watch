//! Save two fixed, process-created YAML versions inside the disposable MSI profile.
use super::{GetFileInformationByHandleEx, emit};
use std::ffi::OsStr;
use std::ffi::c_void;
use std::fs::{File, OpenOptions};
use std::io::{self, BufRead, Read, Seek, Write};
use std::os::windows::ffi::OsStrExt;
use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
use std::os::windows::io::{AsRawHandle, RawHandle};
use std::path::{Path, PathBuf};

const TEST_LOCAL: &str = r"C:\Users\ifw-test\AppData\Local";
const MARKER: &[u8] = b"synthetic-only\n";
const OLD: &[u8] =
    b"serverApiUrl: \"https://127.0.0.1:1/api\"\napiKey: \"synthetic-atomic-old\"\nfolders: []\n";
const NEW: &[u8] =
    b"serverApiUrl: \"https://127.0.0.1:1/api\"\napiKey: \"synthetic-atomic-new\"\nfolders: []\n";
const READ_ATTRIBUTES: u32 = 0x80;
const DELETE: u32 = 0x10000;
const SHARE_DELETE: u32 = 4;
const OPEN_REPARSE_POINT: u32 = 0x00200000;
const BACKUP_SEMANTICS: u32 = 0x02000000;

#[derive(Default, Debug, PartialEq, Eq)]
#[repr(C)]
struct FileId {
    volume: u64,
    id: [u8; 16],
}

#[repr(C)]
struct RenameInfo {
    replace: u32,
    root: RawHandle,
    name_bytes: u32,
    name: [u16; 260],
}

const _: () = assert!(std::mem::offset_of!(RenameInfo, name) == 20);

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetVolumeInformationByHandleW(
        file: RawHandle,
        volume: *mut u16,
        volume_size: u32,
        serial: *mut u32,
        max_component: *mut u32,
        flags: *mut u32,
        name: *mut u16,
        size: u32,
    ) -> i32;
    fn SetFileInformationByHandle(
        file: RawHandle,
        class: i32,
        data: *const c_void,
        size: u32,
    ) -> i32;
}

fn ensure(ok: bool, message: &'static str) -> io::Result<()> {
    if ok {
        Ok(())
    } else {
        Err(io::Error::other(message))
    }
}

fn identity(file: &File) -> io::Result<FileId> {
    let meta = file.metadata()?;
    ensure(
        meta.is_file() && meta.file_attributes() & 0x400 == 0,
        "expected a regular synthetic file",
    )?;
    let mut value = FileId::default();
    // FileIdInfo returns the volume serial number and 128-bit file ID.
    if unsafe {
        GetFileInformationByHandleEx(
            file.as_raw_handle(),
            18,
            (&raw mut value).cast(),
            size_of::<FileId>() as u32,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    ensure(
        value.volume != 0 && value.id != [0; 16],
        "missing file identity",
    )?;
    Ok(value)
}

fn regular_ntfs(root: &File) -> io::Result<()> {
    let mut name = [0u16; 32];
    let null = std::ptr::null_mut();
    if unsafe {
        GetVolumeInformationByHandleW(
            root.as_raw_handle(),
            null,
            0,
            null.cast(),
            null.cast(),
            null.cast(),
            name.as_mut_ptr(),
            name.len() as u32,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    ensure(
        name.starts_with(&[78, 84, 70, 83, 0]),
        "expected the local NTFS test volume",
    )
}

fn profile() -> io::Result<(PathBuf, Vec<File>, File)> {
    ensure(
        std::env::var_os("LOCALAPPDATA").as_deref() == Some(Path::new(TEST_LOCAL).as_os_str()),
        "unexpected disposable user profile",
    )?;
    let dir = Path::new(TEST_LOCAL).join("Immich Folder Watch");
    let mut parents = Vec::new();
    // Keep every directory in the fixed path open without delete sharing.
    for path in dir.ancestors().collect::<Vec<_>>().into_iter().rev() {
        let held = OpenOptions::new()
            .access_mode(READ_ATTRIBUTES)
            .share_mode(3)
            .custom_flags(OPEN_REPARSE_POINT | BACKUP_SEMANTICS)
            .open(path)?;
        let meta = held.metadata()?;
        ensure(
            meta.is_dir() && meta.file_attributes() & 0x400 == 0,
            "unexpected directory or reparse point in the disposable profile",
        )?;
        parents.push(held);
    }
    regular_ntfs(parents.last().expect("the fixed path has a directory"))?;
    let mut marker = OpenOptions::new()
        .read(true)
        .share_mode(1)
        .custom_flags(OPEN_REPARSE_POINT)
        .open(dir.join(".ifw-instance-fixture"))?;
    identity(&marker)?;
    check_bytes(&mut marker, MARKER)?;
    for entry in std::fs::read_dir(&dir)? {
        ensure(
            entry?.file_name() == OsStr::new(".ifw-instance-fixture"),
            "expected a fresh profile containing only its fixture marker",
        )?;
    }
    Ok((dir, parents, marker))
}

fn check_bytes(file: &mut File, expected: &[u8]) -> io::Result<()> {
    ensure(
        file.metadata()?.len() == expected.len() as u64,
        "unexpected synthetic file size",
    )?;
    file.rewind()?;
    let mut actual = vec![0; expected.len()];
    file.read_exact(&mut actual)?;
    ensure(actual == expected, "unexpected synthetic file bytes")
}

fn create(path: &Path, content: &[u8]) -> io::Result<(File, FileId)> {
    // CREATE_NEW never opens or truncates a previous config, temp file or reparse point.
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .access_mode(0xc0000000 | DELETE)
        .share_mode(SHARE_DELETE)
        .custom_flags(OPEN_REPARSE_POINT)
        .open(path)?;
    let id = identity(&file)?;
    file.write_all(content)?;
    file.sync_all()?;
    check_bytes(&mut file, content)?;
    Ok((file, id))
}

fn check_name(path: &Path, expected: &FileId) -> io::Result<()> {
    let named = OpenOptions::new()
        .access_mode(READ_ATTRIBUTES | DELETE)
        .share_mode(7)
        .custom_flags(OPEN_REPARSE_POINT)
        .open(path)?;
    ensure(identity(&named)? == *expected, "the named object changed")?;
    // Probe normal data opens independently. A denied DELETE is already fatal above.
    for access in [0x80000000, 0x40000000] {
        let result = OpenOptions::new()
            .access_mode(access)
            .share_mode(7)
            .custom_flags(OPEN_REPARSE_POINT)
            .open(path);
        match result {
            Err(err) if err.raw_os_error() == Some(32) => (),
            Err(err) => return Err(err),
            Ok(_) => {
                return Err(io::Error::other(
                    "ordinary data access was unexpectedly shared",
                ));
            }
        }
    }
    Ok(())
}

fn command(input: &mut impl BufRead, expected: &str) -> io::Result<()> {
    let mut line = String::new();
    input.read_line(&mut line)?;
    ensure(line.trim_end() == expected, "unexpected fixture command")
}

pub(super) fn trial() -> io::Result<()> {
    let (dir, _parents, _marker) = profile()?;
    let final_path = dir.join("config.yaml");
    let temp_path = dir.join(".ifw-atomic-config.tmp");
    let (mut old, old_id) = create(&final_path, OLD)?;
    let (mut new, new_id) = create(&temp_path, NEW)?;
    ensure(
        old_id.volume == new_id.volume && old_id != new_id,
        "expected separate files on one volume",
    )?;
    check_name(&final_path, &old_id)?;
    check_name(&temp_path, &new_id)?;
    emit(&format!(
        "ATOMIC_PREPARED volume={} old={} new={}",
        old_id.volume,
        u128::from_le_bytes(old_id.id),
        u128::from_le_bytes(new_id.id)
    ))?;
    let mut input = io::stdin().lock();
    command(&mut input, "SAVE")?;
    check_bytes(&mut old, OLD)?;
    check_bytes(&mut new, NEW)?;
    check_name(&final_path, &old_id)?;
    check_name(&temp_path, &new_id)?;
    let encoded: Vec<_> = final_path.as_os_str().encode_wide().collect();
    let mut rename = RenameInfo {
        replace: 1,
        root: std::ptr::null_mut(),
        name_bytes: (encoded.len() * 2) as u32,
        name: [0; 260],
    };
    ensure(
        encoded.len() < rename.name.len(),
        "expected the fixed short test path",
    )?;
    rename.name[..encoded.len()].copy_from_slice(&encoded);
    // FileRenameInfo requests ordinary replacement. Leave both files in place on refusal.
    let renamed = unsafe {
        SetFileInformationByHandle(
            new.as_raw_handle(),
            3,
            (&raw const rename).cast(),
            size_of::<RenameInfo>() as u32,
        )
    };
    if renamed == 0 {
        let error = io::Error::last_os_error();
        check_name(&final_path, &old_id)?;
        check_name(&temp_path, &new_id)?;
        check_bytes(&mut old, OLD)?;
        check_bytes(&mut new, NEW)?;
        emit(&format!("ATOMIC_REFUSED code={:?}", error.raw_os_error()))?;
        return Err(error);
    }
    check_name(&final_path, &new_id)?;
    match std::fs::symlink_metadata(&temp_path) {
        Err(err) if err.raw_os_error() == Some(2) => (),
        Err(err) => return Err(err),
        Ok(_) => return Err(io::Error::other("temporary name survived publication")),
    }
    ensure(
        identity(&old)? == old_id && identity(&new)? == new_id,
        "held identities changed",
    )?;
    check_bytes(&mut old, OLD)?;
    check_bytes(&mut new, NEW)?;
    emit("ATOMIC_SAVED")?;
    command(&mut input, "RELEASE")?;
    drop(old);
    drop(new);
    let mut readback = OpenOptions::new()
        .read(true)
        .share_mode(1)
        .custom_flags(OPEN_REPARSE_POINT)
        .open(final_path)?;
    ensure(
        identity(&readback)? == new_id,
        "published file changed after release",
    )?;
    check_bytes(&mut readback, NEW)?;
    emit("ATOMIC_RELEASED")
}
