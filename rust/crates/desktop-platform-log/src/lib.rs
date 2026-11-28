//! Native desktop log output. The caller owns filtering, redaction, timestamps and file selection.

use std::borrow::Cow;
use std::io::{self, Write};

const FILE_NEWLINE: &str = if cfg!(windows) { "\r\n" } else { "\n" };

#[cfg(windows)]
mod windows;
#[cfg(windows)]
pub use windows::EventLog;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Level {
    Trace,
    Debug,
    Information,
    Warning,
    Error,
    Critical,
}

impl Level {
    fn priority(self) -> u8 {
        match self {
            Self::Trace | Self::Debug => 7,
            Self::Information => 6,
            Self::Warning => 4,
            Self::Error => 3,
            Self::Critical => 2,
        }
    }
}

pub struct Record<'a> {
    pub level: Level,
    pub category: &'a str,
    pub event_id: i32,
    pub message: &'a str,
}

fn journal_field(value: &str) -> Cow<'_, str> {
    if value.contains(['\r', '\n', '\0']) {
        Cow::Owned(value.replace("\r\n", " ").replace(['\r', '\n', '\0'], " "))
    } else {
        Cow::Borrowed(value)
    }
}

impl Record<'_> {
    /// Write one record to a journal-connected console stream with level-prefix parsing enabled.
    pub fn write_systemd(&self, stream: &mut impl Write) -> io::Result<()> {
        write!(
            stream,
            "<{}>{}[{}]",
            self.level.priority(),
            journal_field(self.category),
            self.event_id
        )?;
        if !self.message.is_empty() {
            write!(stream, " {}", journal_field(self.message))?;
        }
        writeln!(stream)?;
        stream.flush()
    }

    /// Append to the caller's opened per-user log and flush through the writer.
    pub fn write_file(&self, file: &mut impl Write, local_timestamp: &str) -> io::Result<()> {
        if self.message.trim().is_empty() {
            return Ok(());
        }
        write!(
            file,
            "{} [{:?}] {}: {}{FILE_NEWLINE}",
            local_timestamp, self.level, self.category, self.message
        )?;
        file.flush()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn journal_lines_have_one_priority_and_one_terminator() {
        for (level, priority) in [
            (Level::Trace, 7),
            (Level::Debug, 7),
            (Level::Information, 6),
            (Level::Warning, 4),
            (Level::Error, 3),
            (Level::Critical, 2),
        ] {
            let record = Record {
                level,
                category: "Desktop",
                event_id: 19,
                message: "Grüße\r\n<0>二\r三\0vier",
            };
            let mut wire = Vec::new();
            record.write_systemd(&mut wire).unwrap();
            assert_eq!(
                wire,
                format!("<{priority}>Desktop[19] Grüße <0>二 三 vier\n").as_bytes()
            );
        }
    }

    #[test]
    fn file_preserves_the_timestamp_level_and_multiline_message() {
        let record = Record {
            level: Level::Warning,
            category: "Desktop",
            event_id: 11,
            message: "Grüße\n二",
        };
        let mut wire = Vec::new();
        record
            .write_file(&mut wire, "2000-01-02 03:04:05.006 +00:00")
            .unwrap();
        assert_eq!(
            wire,
            format!("2000-01-02 03:04:05.006 +00:00 [Warning] Desktop: Grüße\n二{FILE_NEWLINE}")
                .as_bytes()
        );
    }

    #[test]
    fn flush_errors_reach_the_caller() {
        struct BrokenFlush;
        impl Write for BrokenFlush {
            fn write(&mut self, data: &[u8]) -> io::Result<usize> {
                Ok(data.len())
            }
            fn flush(&mut self) -> io::Result<()> {
                Err(io::ErrorKind::BrokenPipe.into())
            }
        }
        let rec = Record {
            level: Level::Information,
            category: "Desktop",
            event_id: 1,
            message: "done",
        };
        assert_eq!(
            rec.write_file(&mut BrokenFlush, "now").unwrap_err().kind(),
            io::ErrorKind::BrokenPipe
        );
        assert_eq!(
            rec.write_systemd(&mut BrokenFlush).unwrap_err().kind(),
            io::ErrorKind::BrokenPipe
        );
    }
}
