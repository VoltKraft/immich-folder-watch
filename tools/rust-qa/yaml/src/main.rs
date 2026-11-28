//! Development-only bounded YAML compatibility assessment.
#![forbid(unsafe_code)]

use ifw_yaml_assessment::{codec, encoding, model};
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
    let byte_reference = match reference["format"].as_str() {
        Some("ifw-rw02-yaml-reference-v1") => false,
        Some("ifw-rw02-yaml-reference-v2") => true,
        _ => return Err("unknown native YAML reference format".into()),
    };
    ensure(
        reference["platform"] == std::env::consts::OS,
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
    let mut byte_checks = 0;
    for row in reference["cases"]
        .as_array()
        .ok_or("missing native cases")?
    {
        let name = row["name"].as_str().ok_or("missing case name")?;
        ensure(fixture_name(name), "invalid case filename")?;
        let expected_text = row["yaml"].as_str().ok_or("missing synthetic YAML")?;
        let decoded = if byte_reference {
            let path = reference_path.join("profile").join(format!("{name}.yaml"));
            let input = encoding::read(
                std::fs::File::open(path)?,
                codec::MAX_FILE_BYTES,
                codec::MAX_TEXT_BYTES,
            )?;
            ensure(
                input.text == expected_text,
                &format!("C#/Rust file decoding differs: {name}"),
            )?;
            ensure(
                row["sourceCodePage"].as_u64() == Some(input.encoding as u64)
                    && row["sourceHadDecodingErrors"].as_bool() == Some(input.had_errors),
                &format!("C#/Rust encoding or fallback differs: {name}"),
            )?;
            byte_checks += 3;
            Some(input)
        } else {
            None
        };
        let source = decoded.as_ref().map_or(expected_text, |input| &input.text);
        let parsed = codec::parse(source, codec::options(), codec::MAX_TEXT_BYTES);
        ensure(
            parsed.is_ok()
                == row["accepted"]
                    .as_bool()
                    .ok_or("missing reference status")?,
            &format!("C#/Rust YAML acceptance differs: {name}"),
        )?;
        checks += 1;
        let mut record = json!({"name":name, "accepted":parsed.is_ok()});
        let read_only = decoded.as_ref().is_some_and(|input| input.had_errors);
        if let Some(input) = decoded {
            record["sourceBytes"] = input.source_bytes.into();
            record["sourceCodePage"] = (input.encoding as u16).into();
            record["sourceHadDecodingErrors"] = input.had_errors.into();
            record["readOnlyOnDecodeError"] = read_only.into();
        }
        let raw = match parsed {
            Ok(raw) => raw,
            Err(error) => {
                record["error"] = error.to_string().into();
                cases.push(record);
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
            codec::parse(independent_written, codec::options(), codec::MAX_TEXT_BYTES)?
                .normalize(&rules)
                == config,
            &format!("C# writer/Rust reader differ: {name}"),
        )?;
        checks += 1;
        record["editingMatched"] = true.into();
        record["runtimeMatched"] = true.into();
        record["csharpWriterMatched"] = true.into();
        cases.push(record);
        if read_only {
            continue;
        }
        for changed in [false, true] {
            if changed {
                config.mutate();
            }
            let yaml = codec::write(&config)?;
            ensure(
                codec::parse(
                    std::str::from_utf8(&yaml)?,
                    codec::options(),
                    codec::MAX_TEXT_BYTES,
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
    }
    let options = codec::options();
    let budget = options
        .budget
        .as_ref()
        .ok_or("missing YAML assessment budget")?;
    let aliases = &options.alias_limits;
    let mut report = json!({"format":"ifw-rw02-yaml-result-v1", "platform":std::env::consts::OS,
        "architecture":std::env::consts::ARCH, "assertions":checks, "cases":cases,
        "limits":{
            "fileBytes":codec::MAX_FILE_BYTES, "inputBytes":budget.max_reader_input_bytes, "outputBytes":codec::MAX_TEXT_BYTES,
            "depth":budget.max_depth, "flowDepth":budget.flow_nesting_limit, "nodes":budget.max_nodes, "events":budget.max_events,
            "scalarBytes":budget.max_total_scalar_bytes, "aliases":budget.max_aliases, "anchors":budget.max_anchors,
            "retainedAnchorEvents":budget.max_recorded_anchor_events, "retainedAnchorBytes":budget.max_recorded_anchor_bytes,
            "replayedEvents":aliases.max_total_replayed_events, "aliasDepth":aliases.max_replay_stack_depth,
            "expansionsPerAnchor":aliases.max_alias_expansions_per_anchor, "documents":budget.max_documents,
            "includeDepth":budget.max_inclusion_depth
        },
        "unproven":["production configuration adapter", "universal Unicode policy", "arbitrary Windows namespace/drive-relative paths",
            "atomic configuration publication and crash recovery", "full migration", "wall-clock/RSS production budget"]});
    if byte_reference {
        report["format"] = "ifw-rw02-yaml-result-v2".into();
        report["byteAssertions"] = byte_checks.into();
    }
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

fn fixture_name(name: &str) -> bool {
    if !name.split('.').all(|part| {
        !part.is_empty() && part.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
    }) {
        return false;
    }
    // Windows interprets device names even with a normal filename extension.
    let stem = name
        .split('.')
        .next()
        .unwrap_or_default()
        .to_ascii_uppercase();
    !matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        && !matches!(
            stem.as_bytes(),
            [b'C', b'O', b'M', b'0'..=b'9'] | [b'L', b'P', b'T', b'0'..=b'9']
        )
}

fn ensure(condition: bool, message: &str) -> Result<(), Box<dyn Error>> {
    if condition {
        Ok(())
    } else {
        Err(message.to_owned().into())
    }
}

#[cfg(test)]
mod tests {
    use super::fixture_name;

    #[test]
    fn case_names_always_identify_ordinary_fixture_files_on_both_platforms() {
        for name in ["unicode.input", "bom-utf16-le", "complete.written"] {
            assert!(fixture_name(name));
        }
        for name in [
            "",
            ".",
            "..",
            "../other",
            r"dir\other",
            "file:stream",
            "a.",
            "NUL",
            "com1.input",
            "Lpt9",
        ] {
            assert!(!fixture_name(name));
        }
    }
}
