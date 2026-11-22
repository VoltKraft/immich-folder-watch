use super::FileIdentity;
use std::io;

pub(super) fn reported(volume: u64, file: u128) -> Option<FileIdentity> {
    // MS-FSCC FileIdInformation reports zero when the provider has no 128-bit ID.
    (file != 0).then_some(FileIdentity { volume, file })
}

pub(super) fn legacy(filesystem: &str, serial: u32, index: u64) -> io::Result<FileIdentity> {
    if ["FAT", "FAT32", "exFAT"]
        .iter()
        .any(|name| name.eq_ignore_ascii_case(filesystem))
        && let Some(id) = reported(serial.into(), index.into())
    {
        return Ok(id);
    }
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "filesystem lacks a supported stable file identifier",
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extended_identity_requires_a_reported_file_id() {
        assert_eq!(reported(25, 0), None);
        let file = 1u128 << 120;
        assert_eq!(reported(0, file), Some(FileIdentity { volume: 0, file }));
    }

    #[test]
    fn legacy_identity_requires_a_known_filesystem_and_a_nonzero_index() {
        for filesystem in ["fat", "FAT32", "exFAT"] {
            let id = legacy(filesystem, 25, u64::MAX).unwrap();
            assert_eq!(id.volume, 25);
            assert_eq!(id.file, u128::from(u64::MAX));
            assert_eq!(
                legacy(filesystem, 25, 0).unwrap_err().kind(),
                io::ErrorKind::Unsupported
            );
        }
        for filesystem in ["NTFS", "ReFS", ""] {
            assert_eq!(
                legacy(filesystem, 25, 1).unwrap_err().kind(),
                io::ErrorKind::Unsupported
            );
        }
    }
}
