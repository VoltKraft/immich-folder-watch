//! Observe the opened body, the fallback identity and the rewound upload body.

use crate::legacy_upload::device_asset_id;
use safe_fs::Directory;
use sha2::{Digest, Sha256};
use std::error::Error;
use std::io::{self, BufRead, Read, Seek, Write};
use std::path::Path;

fn body_digest(file: &mut safe_fs::VerifiedFile) -> io::Result<String> {
    let mut hash = Sha256::new();
    let mut buffer = [0; 16 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            return Ok(crate::legacy_upload::hex(&hash.finalize()).to_ascii_uppercase());
        }
        hash.update(&buffer[..count]);
    }
}

pub fn observe(path: &Path, display: &str) -> Result<(), Box<dyn Error>> {
    let root = Directory::open_root(path)?;
    let mut media = root.open_file("media.jpg".as_ref())?;
    let first = body_digest(&mut media)?;
    println!("BODY_CONSUMED");
    io::stdout().flush()?;
    let mut command = String::new();
    io::stdin().lock().take(16).read_line(&mut command)?;
    if command.trim_end() != "RETRY" {
        return Err("missing synthetic retry".into());
    }
    let current = media.is_current_entry()?;
    let identity = device_asset_id(display, &mut media)?;
    let retry_position = media.stream_position()?;
    let retry = body_digest(&mut media)?;
    println!(
        "{}",
        serde_json::json!({
            "firstBodySha256": first, "originalNameStillMatches": current,
            "identity": identity, "retryPosition": retry_position, "retryBodySha256": retry
        })
    );
    Ok(())
}
