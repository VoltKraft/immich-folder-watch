//! Emit synthetic records for an independent native journal or Event Log reader.

use desktop_platform_log::{Level, Record};
use std::fs::{self, OpenOptions};
use std::io;

fn main() -> io::Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [mode, nonce] = args.as_slice() else {
        return Err(io::Error::other(
            "expected a log target and fixture identifier",
        ));
    };
    if nonce.len() != 32
        || !nonce.bytes().all(|c| c.is_ascii_hexdigit())
        || fs::read_to_string(".ifw-native-log")?.trim_end() != nonce
    {
        return Err(io::Error::other("expected a marked synthetic log profile"));
    }
    #[cfg(windows)]
    let log = {
        let log_name = format!("Q{nonce}");
        let source = format!("IfwQaLog{nonce}");
        match mode.as_str() {
            "event" => Some(desktop_platform_log::EventLog::open(&log_name, &source)?),
            "missing" | "mismatch" => {
                let result = if mode == "missing" {
                    desktop_platform_log::EventLog::open(&log_name, &format!("{source}_absent"))
                } else {
                    desktop_platform_log::EventLog::open(&format!("{log_name}_other"), &source)
                };
                return match result {
                    Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
                    Err(e) => Err(e),
                    Ok(_) => Err(io::Error::other("a missing or misplaced source opened")),
                };
            }
            _ => None,
        }
    };
    let mut console = io::stdout().lock();
    #[cfg(target_os = "linux")]
    if mode == "journal" && std::env::var("IFW_QA_LOG_IDENTITY").as_deref() == Ok("1") {
        use std::io::Write;
        let status = fs::read_to_string("/proc/self/status")?;
        let mut receipt = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open("journal-process")?;
        for line in status
            .lines()
            .filter(|s| s.starts_with("CapEff:") || s.starts_with("NoNewPrivs:"))
        {
            writeln!(receipt, "{line}")?;
        }
    }
    for (i, level) in [
        Level::Trace,
        Level::Debug,
        Level::Information,
        Level::Warning,
        Level::Error,
        Level::Critical,
    ]
    .into_iter()
    .enumerate()
    {
        let message = format!("Grüße 二 {nonce} {i}\nFortsetzung");
        let record = Record {
            level,
            event_id: i as i32 + 100,
            category: "Desktop.Fixture",
            message: &message,
        };
        match mode.as_str() {
            "journal" => record.write_systemd(&mut console)?,
            "file" => {
                let mut output = OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open("synthetic.log")?;
                record.write_file(&mut output, "2000-01-02 03:04:05.006 +00:00")?;
            }
            #[cfg(windows)]
            "event" => log.as_ref().unwrap().write(1, &record)?,
            _ => return Err(io::Error::other("unsupported native log target")),
        }
    }
    Ok(())
}
