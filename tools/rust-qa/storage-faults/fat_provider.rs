//! Development-only ordinary file observation through the unchanged safe-fs API.

use safe_fs::Directory;
use std::ffi::OsStr;
use std::io::{self, Read, Seek, SeekFrom};
use std::path::Path;

const CONTENTS: &[u8] = b"synthetic ordinary safe-fs FAT provider file\n";

fn require(value: bool, message: &'static str) -> io::Result<()> {
    if value {
        Ok(())
    } else {
        Err(io::Error::other(message))
    }
}

fn read_exact_contents(file: &mut impl Read) -> io::Result<()> {
    let mut bytes = [0u8; CONTENTS.len()];
    file.read_exact(&mut bytes)?;
    require(bytes == CONTENTS, "ordinary file contents differed")?;
    require(
        file.read(&mut [0u8; 1])? == 0,
        "ordinary file has extra bytes",
    )
}

fn observe(path: &Path, nonce: &str) -> io::Result<()> {
    require(cfg!(windows), "native Windows provider required")?;
    require(
        nonce.len() == 32
            && nonce.bytes().all(|b| b.is_ascii_hexdigit())
            && path.is_absolute()
            && path.file_name() == Some(OsStr::new(&format!("ifw-provider-{nonce}")))
            && std::env::var_os("IFW_STORAGE_PROVIDER_ROOT").as_deref() == Some(path.as_os_str())
            && std::env::var("IFW_STORAGE_PROVIDER_NONCE").as_deref() == Ok(nonce)
            && std::env::var("GITHUB_ACTIONS").as_deref() == Ok("true")
            && std::env::var("RUNNER_ENVIRONMENT").as_deref() == Ok("github-hosted"),
        "missing private hosted supervisor authority",
    )?;
    let root = Directory::open_root(path)?;
    let mut original = root.open_file(OsStr::new("original.txt"))?;
    let acquired = original.identity();
    require(
        original.is_current_entry()?,
        "new ordinary lease was not current",
    )?;
    require(
        original.metadata()?.len() == CONTENTS.len() as u64,
        "ordinary file length differed",
    )?;
    read_exact_contents(&mut original)?;
    require(
        !path.join("renamed.txt").try_exists()?,
        "rename destination already exists",
    )?;
    // Ordinary fixture setup, not a production rename API or an injected race.
    std::fs::rename(path.join("original.txt"), path.join("renamed.txt"))?;
    require(
        !original.is_current_entry()?,
        "old name remained current after rename",
    )?;
    original.seek(SeekFrom::Start(0))?;
    read_exact_contents(&mut original)?;
    let mut renamed = root.open_file(OsStr::new("renamed.txt"))?;
    let reopened = renamed.identity();
    require(
        renamed.is_current_entry()?,
        "renamed ordinary lease was not current",
    )?;
    require(
        renamed.metadata()?.len() == CONTENTS.len() as u64,
        "renamed file length differed",
    )?;
    read_exact_contents(&mut renamed)?;
    drop(renamed);
    drop(original);
    drop(root);
    // FileIdentity's Debug output contains only the two numeric identifiers.
    // Equality is an observation: FAT may change an index during a rename.
    println!(
        "{{\"format\":\"ifw-safe-fs-fat-provider-v1\",\"opened_read\":true,\"ordinary_rename\":true,\"held_read_after_rename\":true,\"old_name_not_current\":true,\"new_name_reopened_read\":true,\"new_name_current\":true,\"handles_closed\":true,\"acquired_identity\":\"{acquired:?}\",\"reopened_identity\":\"{reopened:?}\",\"identity_changed_on_reopen\":{}}}",
        acquired != reopened
    );
    Ok(())
}

fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let result = match args.as_slice() {
        [path, nonce] => nonce
            .to_str()
            .ok_or_else(|| io::Error::other("nonce must be ASCII"))
            .and_then(|nonce| observe(Path::new(path), nonce)),
        _ => Err(io::Error::other("expected private root and nonce")),
    };
    if let Err(error) = result {
        eprintln!(
            "ordinary provider failed: kind={:?} os={:?}: {error}",
            error.kind(),
            error.raw_os_error()
        );
        std::process::exit(
            if matches!(
                error.kind(),
                io::ErrorKind::PermissionDenied | io::ErrorKind::Unsupported
            ) {
                2
            } else {
                1
            },
        );
    }
}
