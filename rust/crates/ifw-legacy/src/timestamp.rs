//! Exact .NET UTC ticks and canonical SQL `O` text, without floating-point time.

const TICKS_PER_SECOND: u64 = 10_000_000;
const TICKS_PER_DAY: u64 = 86400 * TICKS_PER_SECOND;
const UNIX_EPOCH_TICKS: u64 = 621_355_968_000_000_000;
const MAX_TICKS: u64 = 3_155_378_975_999_999_999;

/// UTC 100-nanosecond ticks since 0001-01-01, in the .NET DateTime range.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct UtcTicks(u64);

/// Invalid representation, calendar date, range, or unrepresentable precision.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TimestampError {
    Format,
    Calendar,
    Range,
    Precision,
}

impl std::fmt::Display for TimestampError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::Format => "invalid legacy timestamp format",
            Self::Calendar => "invalid Gregorian timestamp",
            Self::Range => "timestamp outside .NET range",
            Self::Precision => "timestamp precision is finer than 100 nanoseconds",
        })
    }
}

impl std::error::Error for TimestampError {}

impl UtcTicks {
    /// Reject values outside .NET's year 0001 through 9999 range.
    pub fn from_ticks(ticks: u64) -> Result<Self, TimestampError> {
        if ticks > MAX_TICKS {
            return Err(TimestampError::Range);
        }
        Ok(Self(ticks))
    }

    pub fn ticks(self) -> u64 {
        self.0
    }

    /// Parse only the fixed-width UTC format written by the C# SQLite adapter.
    /// Other offsets, `Z`, and shortened fractions are not canonical SQL values.
    pub fn parse_sql(value: &str) -> Result<Self, TimestampError> {
        let bytes = value.as_bytes();
        if bytes.len() != 33
            || bytes[4] != b'-'
            || bytes[7] != b'-'
            || bytes[10] != b'T'
            || bytes[13] != b':'
            || bytes[16] != b':'
            || bytes[19] != b'.'
            || &bytes[27..] != b"+00:00"
        {
            return Err(TimestampError::Format);
        }
        let year = digits(&bytes[0..4])?;
        let month = digits(&bytes[5..7])?;
        let day = digits(&bytes[8..10])?;
        let hour = digits(&bytes[11..13])?;
        let minute = digits(&bytes[14..16])?;
        let second = digits(&bytes[17..19])?;
        let fraction = digits(&bytes[20..27])?;
        Self::from_calendar([year, month, day], [hour, minute, second], fraction)
    }

    fn from_calendar(
        [year, month, day]: [u32; 3],
        [hour, minute, second]: [u32; 3],
        fraction: u32,
    ) -> Result<Self, TimestampError> {
        if !(1..=9999).contains(&year)
            || !(1..=12).contains(&month)
            || day == 0
            || day > days_in_month(year, month)
            || hour >= 24
            || minute >= 60
            || second >= 60
        {
            return Err(TimestampError::Calendar);
        }
        let days = days_before_year(year)
            + (1..month)
                .map(|m| u64::from(days_in_month(year, m)))
                .sum::<u64>()
            + u64::from(day - 1);
        Self::from_ticks(
            days * TICKS_PER_DAY
                + u64::from(hour * 3600 + minute * 60 + second) * TICKS_PER_SECOND
                + u64::from(fraction),
        )
    }

    /// Match DateTime.FromFileTimeUtc using the UTC calendar returned by Windows
    /// for this FILETIME. Preserve its submillisecond ticks. .NET maps a leap
    /// second to the last representable tick of its minute.
    pub fn from_windows_utc(
        file_time: u64,
        date: [u16; 3],
        [hour, minute, second]: [u16; 3],
        milliseconds: u16,
    ) -> Result<Self, TimestampError> {
        const FILE_TIME_OFFSET: u64 = 504_911_232_000_000_000;
        if file_time > MAX_TICKS - FILE_TIME_OFFSET {
            return Err(TimestampError::Range);
        }
        if milliseconds >= 1000 || second > 60 {
            return Err(TimestampError::Calendar);
        }
        let fraction = if second == 60 {
            9_999_999
        } else {
            u32::from(milliseconds) * 10_000 + (file_time % 10_000) as u32
        };
        Self::from_calendar(
            date.map(u32::from),
            [
                u32::from(hour),
                u32::from(minute),
                u32::from(second.min(59)),
            ],
            fraction,
        )
    }

    /// Parse a UTC DateTimeOffset scalar extracted from repair JSON.
    /// This is not a JSON parser: the audited adapter must first decode the string.
    /// System.Text.Json omits trailing fractional zeros, so 0..=7 digits are allowed.
    pub fn parse_json_utc_scalar(value: &str) -> Result<Self, TimestampError> {
        let body = value.strip_suffix("+00:00").ok_or(TimestampError::Format)?;
        let (whole, fraction) = if let Some((whole, fraction)) = body.split_once('.') {
            if fraction.is_empty()
                || fraction.len() > 7
                || !fraction.bytes().all(|b| b.is_ascii_digit())
            {
                return Err(TimestampError::Format);
            }
            (whole, fraction)
        } else {
            (body, "")
        };
        if whole.len() != 19 {
            return Err(TimestampError::Format);
        }
        let padded = format!("{whole}.{fraction:0<7}+00:00");
        Self::parse_sql(&padded)
    }

    /// Emit UTC `.NET O` text with seven fractional digits for lexical SQL ordering.
    pub fn format_sql(self) -> String {
        let mut days = self.0 / TICKS_PER_DAY;
        let mut low = 1;
        let mut high = 10_000;
        while low + 1 < high {
            let middle = (low + high) / 2;
            if days_before_year(middle) <= days {
                low = middle;
            } else {
                high = middle;
            }
        }
        let year = low;
        days -= days_before_year(year);
        let mut month = 1;
        while days >= u64::from(days_in_month(year, month)) {
            days -= u64::from(days_in_month(year, month));
            month += 1;
        }
        let day = days + 1;
        let remainder = self.0 % TICKS_PER_DAY;
        let seconds = remainder / TICKS_PER_SECOND;
        let hour = seconds / 3600;
        let minute = (seconds % 3600) / 60;
        let second = seconds % 60;
        let fraction = remainder % TICKS_PER_SECOND;
        format!(
            "{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}.{fraction:07}+00:00"
        )
    }

    /// Format the UTC scalar produced by System.Text.Json's DateTimeOffset writer.
    pub fn format_json_utc_scalar(self) -> String {
        let sql = self.format_sql();
        let fraction = sql[20..27].trim_end_matches('0');
        if fraction.is_empty() {
            format!("{}+00:00", &sql[..19])
        } else {
            format!("{}.{fraction}+00:00", &sql[..19])
        }
    }

    /// Convert floor-based Unix seconds plus a nonnegative subsecond fraction.
    /// Reject rather than silently truncate filesystem precision finer than .NET ticks.
    pub fn from_unix_time(seconds: i64, nanoseconds: u32) -> Result<Self, TimestampError> {
        if nanoseconds >= 1_000_000_000 {
            return Err(TimestampError::Range);
        }
        if !nanoseconds.is_multiple_of(100) {
            return Err(TimestampError::Precision);
        }
        let ticks = i128::from(UNIX_EPOCH_TICKS)
            + i128::from(seconds) * i128::from(TICKS_PER_SECOND)
            + i128::from(nanoseconds / 100);
        if ticks < 0 || ticks > i128::from(MAX_TICKS) {
            return Err(TimestampError::Range);
        }
        Ok(Self(ticks as u64))
    }

    /// Match the shipping Linux worker's last-write tick for an open file.
    /// Linux supplies whole seconds and a nonnegative nanosecond fraction.
    /// The worker keeps the complete 100 ns ticks in that fraction, including
    /// for files dated before 1970. Persisted timestamps use the exact codec.
    #[cfg(target_os = "linux")]
    pub fn from_linux_mtime(metadata: &std::fs::Metadata) -> Result<Self, TimestampError> {
        use std::os::unix::fs::MetadataExt;

        let nanos = u32::try_from(metadata.mtime_nsec()).map_err(|_| TimestampError::Range)?;
        Self::from_unix_time(metadata.mtime(), nanos - nanos % 100)
    }

    /// Return Unix seconds and nanoseconds with a nonnegative remainder before 1970 too.
    pub fn to_unix_time(self) -> (i64, u32) {
        let difference = i128::from(self.0) - i128::from(UNIX_EPOCH_TICKS);
        (
            difference.div_euclid(i128::from(TICKS_PER_SECOND)) as i64,
            (difference.rem_euclid(i128::from(TICKS_PER_SECOND)) * 100) as u32,
        )
    }
}

fn digits(bytes: &[u8]) -> Result<u32, TimestampError> {
    bytes.iter().try_fold(0, |value, byte| {
        if byte.is_ascii_digit() {
            Ok(value * 10 + u32::from(byte - b'0'))
        } else {
            Err(TimestampError::Format)
        }
    })
}

fn days_before_year(year: u32) -> u64 {
    let y = u64::from(year - 1);
    365 * y + y / 4 - y / 100 + y / 400
}

fn days_in_month(year: u32, month: u32) -> u32 {
    match month {
        2 if year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400)) => {
            29
        }
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn windows_file_times_keep_submillisecond_ticks_and_clamp_a_leap_second() {
        let date = [2016, 12, 31];
        let file_time = 131_277_023_999_991_234;
        let sample = UtcTicks::from_windows_utc(file_time, date, [23, 59, 59], 999).unwrap();
        assert_eq!(sample.format_sql(), "2016-12-31T23:59:59.9991234+00:00");
        let leap = UtcTicks::from_windows_utc(file_time, date, [23, 59, 60], 0).unwrap();
        assert_eq!(leap.format_sql(), "2016-12-31T23:59:59.9999999+00:00");
        assert_eq!(
            UtcTicks::from_windows_utc(2_650_467_744_000_000_000, date, [0, 0, 0], 0),
            Err(TimestampError::Range)
        );
    }

    #[test]
    fn extremes_and_pre_unix_epoch_retain_every_tick() {
        for (text, ticks) in [
            ("0001-01-01T00:00:00.0000000+00:00", 0),
            ("1970-01-01T00:00:00.0000000+00:00", UNIX_EPOCH_TICKS),
            ("1969-12-31T23:59:59.9999999+00:00", UNIX_EPOCH_TICKS - 1),
            ("9999-12-31T23:59:59.9999999+00:00", MAX_TICKS),
        ] {
            let value = UtcTicks::parse_sql(text).unwrap();
            assert_eq!(value.ticks(), ticks);
            assert_eq!(value.format_sql(), text);
            let (seconds, nanos) = value.to_unix_time();
            assert_eq!(UtcTicks::from_unix_time(seconds, nanos).unwrap(), value);
        }
        assert_eq!(
            UtcTicks(UNIX_EPOCH_TICKS - 1).to_unix_time(),
            (-1, 999_999_900)
        );
    }

    #[test]
    fn malformed_noncanonical_and_impossible_dates_are_rejected() {
        for text in [
            "1900-02-29T00:00:00.0000000+00:00",
            "2024-02-30T00:00:00.0000000+00:00",
            "0000-01-01T00:00:00.0000000+00:00",
            "2024-01-01T24:00:00.0000000+00:00",
            "2024-01-01T00:00:60.0000000+00:00",
            "2024-01-01T00:00:00.0000000Z",
            "2024-01-01T00:00:00.0+00:00",
            "2024-01-01T00:00:00.0000000+01:00",
            "２０２４-01-01T00:00:00.0000000+00:00",
            "2024-01-01T00:00:00.0000000+00:00\n",
        ] {
            assert!(UtcTicks::parse_sql(text).is_err(), "{text}");
        }
        assert!(UtcTicks::parse_sql("2000-02-29T00:00:00.0000000+00:00").is_ok());
    }

    #[test]
    fn json_fraction_codec_does_not_change_sql_precision() {
        for json in [
            "2024-02-29T12:00:00+00:00",
            "2024-02-29T12:00:00.12+00:00",
            "2024-02-29T12:00:00.0000001+00:00",
        ] {
            let value = UtcTicks::parse_json_utc_scalar(json).unwrap();
            assert_eq!(value.format_json_utc_scalar(), json);
            assert_eq!(UtcTicks::parse_sql(&value.format_sql()).unwrap(), value);
        }
        assert!(UtcTicks::parse_json_utc_scalar("2024-02-29T12:00:00.+00:00").is_err());
        assert!(UtcTicks::parse_json_utc_scalar("2024-02-29T12:00:00.12345678+00:00").is_err());
    }

    #[test]
    fn invalid_ranges_and_subtick_precision_do_not_silently_round() {
        assert_eq!(UtcTicks::from_ticks(u64::MAX), Err(TimestampError::Range));
        assert_eq!(
            UtcTicks::from_unix_time(0, 1),
            Err(TimestampError::Precision)
        );
        assert_eq!(
            UtcTicks::from_unix_time(0, 1_000_000_000),
            Err(TimestampError::Range)
        );
        assert_eq!(
            UtcTicks::from_unix_time(i64::MIN, 0),
            Err(TimestampError::Range)
        );
        assert_eq!(
            UtcTicks::from_unix_time(i64::MAX, 0),
            Err(TimestampError::Range)
        );
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_file_times_keep_complete_ticks_on_either_side_of_the_epoch() {
        use std::fs::File;
        use std::os::unix::fs::MetadataExt;
        use std::time::{Duration, UNIX_EPOCH};

        let path = std::env::temp_dir().join(format!("ifw-mtime-{}", std::process::id()));
        let file = File::create_new(&path).unwrap();
        std::fs::remove_file(&path).unwrap();
        for (offset_ns, expected_ticks) in [
            (-101_i64, -2_i64),
            (-100, -1),
            (-1, -1),
            (0, 0),
            (1, 0),
            (99, 0),
            (100, 1),
            (199, 1),
            (999_999_999, 9_999_999),
        ] {
            let difference = Duration::from_nanos(offset_ns.unsigned_abs());
            let instant = if offset_ns < 0 {
                UNIX_EPOCH - difference
            } else {
                UNIX_EPOCH + difference
            };
            file.set_modified(instant).unwrap();
            let metadata = file.metadata().unwrap();
            assert_eq!(metadata.mtime(), offset_ns.div_euclid(1_000_000_000));
            assert_eq!(metadata.mtime_nsec(), offset_ns.rem_euclid(1_000_000_000));
            assert_eq!(
                UtcTicks::from_linux_mtime(&metadata).unwrap().ticks(),
                UNIX_EPOCH_TICKS.checked_add_signed(expected_ticks).unwrap()
            );
        }
    }
}
