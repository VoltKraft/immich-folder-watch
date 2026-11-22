//! Synthetic line-oriented RW-02 test adapter, not the application CLI.

use ifw_legacy::casing::ReferenceCaseMap;
use ifw_legacy::paths::{normalize_absolute_source, normalize_relative_text};
use ifw_legacy::timestamp::UtcTicks;
use ifw_legacy::{EntryStatus, TransferDirection};
use std::io::{self, BufRead, Read, Write};
use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let map_path = args
        .next()
        .ok_or("usage: legacy-probe <synthetic-casing-map>")?;
    if args.next().is_some() {
        return Err("unexpected extra arguments".into());
    }
    let map = read_map(Path::new(&map_path))?;
    let mut input = io::stdin().lock();
    let mut output = io::BufWriter::new(io::stdout().lock());
    loop {
        let mut line = Vec::new();
        let read = (&mut input).take(300_001).read_until(b'\n', &mut line)?;
        if read == 0 {
            break;
        }
        if read > 300_000 {
            return Err("probe request exceeds limit".into());
        }
        let line = std::str::from_utf8(&line)?.trim_end_matches(['\r', '\n']);
        match handle(line, &map) {
            Ok(result) => writeln!(output, "ok\t{result}")?,
            Err(()) => writeln!(output, "err")?,
        }
    }
    output.flush()?;
    Ok(())
}

fn read_map(path: &Path) -> Result<ReferenceCaseMap, Box<dyn std::error::Error>> {
    let mut bytes = Vec::new();
    std::fs::File::open(path)?
        .take(200_001)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 200_000 {
        return Err("reference map exceeds limit".into());
    }
    Ok(ReferenceCaseMap::from_reference_tsv(std::str::from_utf8(
        &bytes,
    )?)?)
}

fn handle(line: &str, map: &ReferenceCaseMap) -> Result<String, ()> {
    let fields: Vec<_> = line.split('\t').collect();
    match fields.as_slice() {
        ["platform"] => Ok(format!(
            "{}\t{}",
            std::env::consts::OS,
            std::env::consts::ARCH
        )),
        ["sql", value] => time_result(UtcTicks::parse_sql(value).map_err(|_| ())?),
        ["json-time", value] => {
            time_result(UtcTicks::parse_json_utc_scalar(value).map_err(|_| ())?)
        }
        ["ticks", value] => {
            time_result(UtcTicks::from_ticks(value.parse().map_err(|_| ())?).map_err(|_| ())?)
        }
        ["unix", seconds, nanos] => time_result(
            UtcTicks::from_unix_time(
                seconds.parse().map_err(|_| ())?,
                nanos.parse().map_err(|_| ())?,
            )
            .map_err(|_| ())?,
        ),
        ["direction", value] => Ok((TransferDirection::try_from(
            value.parse::<i64>().map_err(|_| ())?,
        )
        .map_err(|_| ())? as i64)
            .to_string()),
        ["status", value] => Ok(
            (EntryStatus::try_from(value.parse::<i64>().map_err(|_| ())?).map_err(|_| ())? as i64)
                .to_string(),
        ),
        ["uppercase", value] => {
            let input = decode_utf16_hex(value)?;
            Ok(encode_utf16_hex(&map.uppercase_utf16(&input)))
        }
        ["source", input] => {
            let input = decode_text(input)?;
            let normalized = normalize_absolute_source(Path::new(&input)).map_err(|_| ())?;
            Ok(encode_text(normalized.to_str().ok_or(())?))
        }
        ["relative", input] => Ok(encode_text(
            &normalize_relative_text(&decode_text(input)?).map_err(|_| ())?,
        )),
        ["key", case_sensitive, input] => {
            let input = decode_text(input)?;
            match *case_sensitive {
                "true" => Ok(encode_text(&input)),
                "false" => Ok(encode_text(&map.uppercase(&input))),
                _ => Err(()),
            }
        }
        _ => Err(()),
    }
}

fn time_result(value: UtcTicks) -> Result<String, ()> {
    let (seconds, nanos) = value.to_unix_time();
    Ok(format!(
        "{}\t{}\t{seconds}\t{nanos}\t{}",
        value.ticks(),
        value.format_sql(),
        value.format_json_utc_scalar()
    ))
}

fn decode_text(value: &str) -> Result<String, ()> {
    if !value.len().is_multiple_of(2) || !value.is_ascii() {
        return Err(());
    }
    let bytes: Result<Vec<_>, _> = (0..value.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&value[index..index + 2], 16))
        .collect();
    String::from_utf8(bytes.map_err(|_| ())?).map_err(|_| ())
}

fn encode_text(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn decode_utf16_hex(value: &str) -> Result<Vec<u16>, ()> {
    if !value.len().is_multiple_of(4) || !value.is_ascii() {
        return Err(());
    }
    (0..value.len())
        .step_by(4)
        .map(|index| u16::from_str_radix(&value[index..index + 4], 16).map_err(|_| ()))
        .collect()
}

fn encode_utf16_hex(value: &[u16]) -> String {
    value.iter().map(|unit| format!("{unit:04X}")).collect()
}
