//! Legacy Immich upload identity for an already authorized, reusable file lease.

use ifw_legacy::timestamp::UtcTicks;
use safe_fs::VerifiedFile;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fmt::Write as _;
use std::io::{self, Read, Seek};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LegacyUploadId {
    pub length: u64,
    pub last_write_ticks: u64,
    pub content_sha256: String,
    pub device_asset_id: String,
}

/// Hash from byte zero, then rewind the same lease for the subsequent upload.
/// The display string contributes verbatim UTF-8 bytes to the legacy identity.
/// All reads, seeks and metadata queries use the supplied open file.
pub fn device_asset_id(display_path: &str, file: &mut VerifiedFile) -> io::Result<LegacyUploadId> {
    let mut content_sha256 = hash_and_rewind(file)?;
    content_sha256.make_ascii_uppercase();
    let metadata = file.metadata()?;
    let length = metadata.len();
    #[cfg(target_os = "linux")]
    let modified = UtcTicks::from_linux_mtime(&metadata);
    #[cfg(windows)]
    let modified = {
        let utc = safe_fs::WindowsWriteTime::from_metadata(&metadata)?;
        UtcTicks::from_windows_utc(utc.file_time, utc.date, utc.time, utc.milliseconds)
    };
    let last_write_ticks = modified
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?
        .ticks();
    let mut identity = Sha256::new();
    identity.update(display_path.as_bytes());
    identity.update(format!("|{length}|{last_write_ticks}|{content_sha256}").as_bytes());
    Ok(LegacyUploadId {
        length,
        last_write_ticks,
        content_sha256,
        device_asset_id: hex(&identity.finalize()),
    })
}

fn hash_and_rewind(reader: &mut (impl Read + Seek)) -> io::Result<String> {
    reader.rewind()?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 16 * 1024];
    let read_result = loop {
        match reader.read(&mut buffer) {
            Ok(0) => break Ok(()),
            Ok(n) => hash.update(&buffer[..n]),
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => break Err(error),
        }
    };
    let rewind_result = reader.rewind();
    read_result?;
    rewind_result?;
    Ok(hex(&hash.finalize()))
}

pub(super) fn hex(bytes: &[u8]) -> String {
    let mut text = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        write!(text, "{byte:02x}").expect("writing to a String is infallible");
    }
    text
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Cursor, SeekFrom};

    struct ReadFault {
        data: Cursor<Vec<u8>>,
        error: Option<io::ErrorKind>,
    }

    impl Read for ReadFault {
        fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
            if self.data.position() > 0
                && let Some(error) = self.error.take()
            {
                return Err(error.into());
            }
            self.data.read(buffer)
        }
    }

    impl Seek for ReadFault {
        fn seek(&mut self, pos: SeekFrom) -> io::Result<u64> {
            self.data.seek(pos)
        }
    }

    #[test]
    fn hashes_empty_and_multibuffer_inputs_from_the_start_and_rewinds() {
        for data in [Vec::new(), vec![0xab; 131_073]] {
            let expected = hex(&Sha256::digest(&data));
            let mut file = ReadFault {
                data: Cursor::new(data),
                error: Some(io::ErrorKind::Interrupted),
            };
            file.seek(SeekFrom::End(0)).unwrap();
            assert_eq!(hash_and_rewind(&mut file).unwrap(), expected);
            assert_eq!(file.data.position(), 0);
        }
    }

    #[test]
    fn later_read_error_is_returned_and_the_lease_rewinds() {
        let mut file = ReadFault {
            data: Cursor::new(vec![31; 40_000]),
            error: Some(io::ErrorKind::PermissionDenied),
        };
        assert_eq!(
            hash_and_rewind(&mut file).unwrap_err().kind(),
            io::ErrorKind::PermissionDenied
        );
        assert_eq!(file.data.position(), 0);
    }
}
