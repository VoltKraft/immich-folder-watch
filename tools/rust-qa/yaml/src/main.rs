//! Development-only bounded YAML compatibility assessment.
#![forbid(unsafe_code)]

mod codec;
mod model;

use model::{Casing, TextRules};
use serde_json::{Value, json};
use std::error::Error;
use std::io::Write;
use std::path::{Path, PathBuf};

fn main() -> Result<(), Box<dyn Error>> {
    let arguments: Vec<_> = std::env::args_os().skip(1).collect();
    if arguments.len() != 2 {
        return Err("usage: ifw-yaml-assessment <native-reference> <new-output>".into());
    }
    let reference_path = PathBuf::from(&arguments[0]);
    let output = PathBuf::from(&arguments[1]);
    let reference: Value =
        serde_json::from_slice(&std::fs::read(reference_path.join("reference.json"))?)?;
    ensure(
        reference["format"] == "ifw-rw02-yaml-reference-v1"
            && reference["platform"] == std::env::consts::OS,
        "wrong native YAML reference",
    )?;
    let architecture = if cfg!(target_arch = "x86_64") {
        "X64"
    } else {
        "Arm64"
    };
    ensure(
        reference["architecture"] == architecture && reference["osArchitecture"] == architecture,
        "wrong native YAML architecture",
    )?;
    let casing: Casing =
        serde_json::from_slice(&std::fs::read(reference_path.join("casing.json"))?)?;
    let rules = TextRules::from_reference(casing)?;
    let profile = Path::new(
        reference["profile"]
            .as_str()
            .ok_or("missing synthetic profile")?,
    );
    std::fs::create_dir(&output)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&output, std::fs::Permissions::from_mode(0o700))?;
    }
    let mut cases = Vec::new();
    let mut checks = 0;
    for row in reference["cases"]
        .as_array()
        .ok_or("missing native cases")?
    {
        let name = row["name"].as_str().ok_or("missing case name")?;
        ensure(
            name.bytes()
                .all(|value| value.is_ascii_alphanumeric() || matches!(value, b'-' | b'.')),
            "invalid case output filename",
        )?;
        let source = row["yaml"].as_str().ok_or("missing synthetic YAML")?;
        let parsed = codec::parse(source, codec::options(), codec::MAX_BYTES);
        ensure(
            parsed.is_ok()
                == row["accepted"]
                    .as_bool()
                    .ok_or("missing reference status")?,
            &format!("C#/Rust YAML acceptance differs: {name}"),
        )?;
        checks += 1;
        let raw = match parsed {
            Ok(raw) => raw,
            Err(error) => {
                cases.push(json!({"name":name,"accepted":false,"error":error.to_string()}));
                continue;
            }
        };
        let mut config = raw.normalize(&rules);
        ensure(
            serde_json::to_value(&config)? == row["editable"],
            &format!("C#/Rust editing values differ: {name}"),
        )?;
        ensure(
            serde_json::to_value(config.runtime(profile)?)? == row["runtime"],
            &format!("C#/Rust runtime paths differ: {name}"),
        )?;
        checks += 2;
        let independent_written = row["written"].as_str().ok_or("missing C# writer result")?;
        ensure(
            codec::parse(independent_written, codec::options(), codec::MAX_BYTES)?
                .normalize(&rules)
                == config,
            &format!("C# writer/Rust reader differ: {name}"),
        )?;
        checks += 1;
        for changed in [false, true] {
            if changed {
                config.mutate();
            }
            let yaml = codec::write(&config)?;
            ensure(
                codec::parse(
                    std::str::from_utf8(&yaml)?,
                    codec::options(),
                    codec::MAX_BYTES,
                )?
                .normalize(&rules)
                    == config,
                &format!("Rust YAML roundtrip differs: {name}"),
            )?;
            checks += 1;
            let mut file = std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(output.join(format!(
                    "{name}.{}.yaml",
                    if changed { "changed" } else { "roundtrip" }
                )))?;
            file.write_all(&yaml)?;
        }
        cases.push(json!({"name":name,"accepted":true,"editingMatched":true,"runtimeMatched":true,"csharpWriterMatched":true}));
    }
    let report = json!({"format":"ifw-rw02-yaml-result-v1", "platform":std::env::consts::OS,
        "architecture":std::env::consts::ARCH, "assertions":checks, "cases":cases,
        "limits":{"inputBytes":codec::MAX_BYTES,"outputBytes":codec::MAX_BYTES,"depth":16,"nodes":2048,
            "events":4096,"scalarBytes":32768,"aliases":32,"anchors":32,"retainedAnchorEvents":4096,
            "retainedAnchorBytes":65536,"replayedEvents":4096,"aliasDepth":16,"expansionsPerAnchor":32,"documents":1},
        "unproven":["production configuration adapter", "universal Unicode policy", "arbitrary Windows namespace/drive-relative paths",
            "atomic configuration publication and crash recovery", "full migration", "wall-clock/RSS production budget"]});
    std::fs::write(
        output.join("result.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    println!(
        "Native YAML assessment passed: {} cases, {checks} differential assertions.",
        cases.len()
    );
    Ok(())
}

fn ensure(condition: bool, message: &str) -> Result<(), Box<dyn Error>> {
    if condition {
        Ok(())
    } else {
        Err(message.to_owned().into())
    }
}
