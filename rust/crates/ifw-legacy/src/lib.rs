//! Legacy storage scalar codecs. Path identities here never authorize filesystem access.
//!
//! SQLite, YAML, repair JSON and cryptographic adapters are intentionally not supplied
//! by this dependency-free feasibility crate. Preserve their raw data until those
//! separately audited adapters are qualified against the C# corpus.
#![forbid(unsafe_code)]

pub mod casing;
pub mod paths;
pub mod timestamp;

/// Persisted `sync_entries.direction`; unknown future values are rejected.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(i64)]
pub enum TransferDirection {
    Upload = 0,
    Download = 1,
}

/// Persisted `sync_entries.status`; unknown future values are rejected.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(i64)]
pub enum EntryStatus {
    Synchronized = 0,
    Tombstone = 1,
}

/// An unrecognized persisted enum value, without including surrounding user data.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct UnknownEnumValue;

impl std::fmt::Display for UnknownEnumValue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("unknown legacy enum value")
    }
}

impl std::error::Error for UnknownEnumValue {}

impl TryFrom<i64> for TransferDirection {
    type Error = UnknownEnumValue;

    fn try_from(value: i64) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::Upload),
            1 => Ok(Self::Download),
            _ => Err(UnknownEnumValue),
        }
    }
}

impl TryFrom<i64> for EntryStatus {
    type Error = UnknownEnumValue;

    fn try_from(value: i64) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::Synchronized),
            1 => Ok(Self::Tombstone),
            _ => Err(UnknownEnumValue),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn persisted_enum_values_are_closed() {
        assert_eq!(
            TransferDirection::try_from(0),
            Ok(TransferDirection::Upload)
        );
        assert_eq!(
            TransferDirection::try_from(1),
            Ok(TransferDirection::Download)
        );
        assert_eq!(EntryStatus::try_from(0), Ok(EntryStatus::Synchronized));
        assert_eq!(EntryStatus::try_from(1), Ok(EntryStatus::Tombstone));
        for invalid in [i64::MIN, -1, 2, i64::MAX] {
            assert!(TransferDirection::try_from(invalid).is_err());
            assert!(EntryStatus::try_from(invalid).is_err());
        }
    }
}
