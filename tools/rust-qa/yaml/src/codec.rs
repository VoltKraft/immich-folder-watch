//! Real serde-saphyr parsing with explicit bounded input, work and output.

use crate::model::{Config, RawConfig};
use serde_json::Value;
use serde_saphyr::{DuplicateKeyPolicy, MergeKeyPolicy, Options};
use std::io::Write;

/// UTF-8 text on input and output. A UTF-32 file may need four bytes per
/// ASCII character plus its BOM for the same admitted document.
pub const MAX_TEXT_BYTES: usize = 256 * 1024;
pub const MAX_FILE_BYTES: usize = 4 * MAX_TEXT_BYTES + 4;

#[derive(Debug, PartialEq, Eq)]
pub enum Failure {
    InputBytes,
    InputIo(std::io::ErrorKind),
    Budget,
    InvalidYaml,
    InvalidDocument,
    OutputBytes,
}

impl std::fmt::Display for Failure {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Never render the parser's input-bearing snippets, tag text or scalar values.
        write!(formatter, "YAML {:?}", self)
    }
}

impl std::error::Error for Failure {}

pub fn options() -> Options {
    let mut options = serde_saphyr::options! {
        budget: serde_saphyr::budget! {
            max_reader_input_bytes: Some(MAX_TEXT_BYTES), max_depth: 16, flow_nesting_limit: 16,
            max_nodes: 16_384, max_events: 32_768, max_documents: 1,
            max_total_scalar_bytes: 128 * 1024, max_aliases: 32, max_anchors: 32,
            max_recorded_anchor_events: 4096, max_recorded_anchor_bytes: 65_536,
            max_inclusion_depth: 0,
        },
        duplicate_keys: DuplicateKeyPolicy::LastWins,
        merge_keys: MergeKeyPolicy::AsOrdinary,
        reject_unsupported_tags: true,
        // YamlDotNet writes U+FEFF at the start of a plain album name verbatim.
        bom_inside_document_as_content: true,
        strict_booleans: false,
        legacy_octal_numbers: true,
        with_snippet: false,
    };
    options.alias_limits.max_total_replayed_events = 4096;
    options.alias_limits.max_replay_stack_depth = 16;
    options.alias_limits.max_alias_expansions_per_anchor = 32;
    options
}

pub(super) fn classify(error: serde_saphyr::Error) -> Failure {
    use serde_saphyr::Error;
    match error {
        Error::Budget { .. }
        | Error::AliasReplayCounterOverflow { .. }
        | Error::AliasReplayLimitExceeded { .. }
        | Error::AliasExpansionLimitExceeded { .. }
        | Error::AliasReplayStackDepthExceeded { .. } => Failure::Budget,
        Error::AliasError { error, .. } | Error::WithSnippet { error, .. } => classify(*error),
        _ => Failure::InvalidYaml,
    }
}

pub fn parse(input: &str, mut options: Options, max_bytes: usize) -> Result<RawConfig, Failure> {
    if input.len() > max_bytes {
        return Err(Failure::InputBytes);
    }
    let anchors = crate::anchors::compatible_input(input, &mut options)?;
    let view = crate::scalar_breaks::compatible_input(&anchors, &options)?;
    serde_saphyr::from_str_with_options::<Option<RawConfig>>(&view, options)
        .map_err(classify)?
        .ok_or(Failure::InvalidDocument)
}

pub fn write(config: &Config) -> Result<Vec<u8>, Failure> {
    let mut value = serde_json::to_value(config).map_err(|_| Failure::InvalidDocument)?;
    value["watch"]
        .as_object_mut()
        .ok_or(Failure::InvalidDocument)?
        .remove("extensions");
    write_value(&value, MAX_TEXT_BYTES)
}

fn write_value(value: &Value, limit: usize) -> Result<Vec<u8>, Failure> {
    struct LimitedWriter {
        bytes: Vec<u8>,
        limit: usize,
    }
    impl Write for LimitedWriter {
        fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
            if bytes.len() > self.limit.saturating_sub(self.bytes.len()) {
                return Err(std::io::Error::other("YAML output limit exceeded"));
            }
            self.bytes.extend_from_slice(bytes);
            Ok(bytes.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }
    let mut writer = LimitedWriter {
        bytes: Vec::new(),
        limit,
    };
    serde_saphyr::to_io_writer_with_options(
        &mut writer,
        value,
        serde_saphyr::ser_options! { quote_all: true },
    )
    .map_err(|_| Failure::OutputBytes)?;
    Ok(writer.bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn budget_pair(input: &str, restrict: impl FnOnce(&mut Options)) {
        assert!(parse(input, options(), MAX_TEXT_BYTES).is_ok());
        let mut limited = options();
        restrict(&mut limited);
        assert!(matches!(
            parse(input, limited, MAX_TEXT_BYTES),
            Err(Failure::Budget)
        ));
    }

    #[test]
    fn input_and_output_byte_boundaries_are_enforced() {
        assert!(parse("{}", options(), 2).is_ok());
        assert!(matches!(
            parse("{}", options(), 1),
            Err(Failure::InputBytes)
        ));
        let value = serde_json::json!({"value":"日本語 😀: # null"});
        let encoded = write_value(&value, MAX_TEXT_BYTES).unwrap();
        assert_eq!(write_value(&value, encoded.len()).unwrap(), encoded);
        assert_eq!(
            write_value(&value, encoded.len() - 1),
            Err(Failure::OutputBytes)
        );
    }

    #[test]
    fn unknown_fields_still_obey_depth_node_event_and_scalar_budgets() {
        budget_pair("future: [[[one]]]", |options| {
            options.budget.as_mut().unwrap().max_depth = 2
        });
        budget_pair("future: [one, two, three]", |options| {
            options.budget.as_mut().unwrap().max_nodes = 3
        });
        budget_pair("future: [one, two, three]", |options| {
            options.budget.as_mut().unwrap().max_events = 4
        });
        budget_pair("future: secret-synthetic-do-not-echo", |options| {
            options.budget.as_mut().unwrap().max_total_scalar_bytes = 8
        });
    }

    #[test]
    fn anchor_retention_and_replay_have_independent_budgets() {
        let input = "watch: {sources: [&s {path: media}, *s, *s]}";
        budget_pair(input, |options| {
            options.budget.as_mut().unwrap().max_aliases = 1
        });
        budget_pair(input, |options| {
            options.budget.as_mut().unwrap().max_recorded_anchor_events = 2
        });
        budget_pair(input, |options| {
            options.alias_limits.max_total_replayed_events = 2
        });
        budget_pair(input, |options| {
            options.alias_limits.max_alias_expansions_per_anchor = 1
        });
        budget_pair("future: [&one a, &two b]", |options| {
            options.budget.as_mut().unwrap().max_anchors = 1
        });
        budget_pair(
            "watch: {sources: [&s {path: \"owned\\nscalar\"}, *s]}",
            |options| options.budget.as_mut().unwrap().max_recorded_anchor_bytes = 2,
        );
    }

    #[test]
    fn skipped_symbols_still_consume_alias_anchor_replay_and_content_budgets() {
        let input = "future: [&item [one, two], *unbound, *item]";
        budget_pair(input, |options| {
            options.budget.as_mut().unwrap().max_aliases = 1
        });
        budget_pair(input, |options| {
            options.alias_limits.max_total_replayed_events = 2
        });
        budget_pair(input, |options| {
            options.budget.as_mut().unwrap().max_recorded_anchor_events = 2
        });
        budget_pair("future: {*missing : value, other: *unknown}", |options| {
            options.budget.as_mut().unwrap().alias_anchor_min_aliases = 2
        });
        budget_pair("future: [*unbound, &a 1, &b 2]", |options| {
            options.budget.as_mut().unwrap().max_anchors = 1
        });
        budget_pair("future: {child: [*unbound, [one]]}", |options| {
            options.budget.as_mut().unwrap().max_depth = 3
        });
        budget_pair("future: [*unbound, large-scalar]", |options| {
            options.budget.as_mut().unwrap().max_total_scalar_bytes = 10
        });
        budget_pair("future: [*unbound, one, two]", |options| {
            options.budget.as_mut().unwrap().max_nodes = 4
        });
        budget_pair("future: [*unbound, one, two]", |options| {
            options.budget.as_mut().unwrap().max_events = 5
        });
        for yaml in [
            "future: [*unbound, !include synthetic]",
            "future: [*unbound, &recursive [*recursive]]",
        ] {
            assert!(parse(yaml, options(), MAX_TEXT_BYTES).is_err());
        }
    }

    #[test]
    fn legacy_breaks_charge_original_bytes_and_the_full_decoded_scalar() {
        let input = "future: >-\n  a\u{2028}  b\n";
        assert!(matches!(
            parse(input, options(), input.len() - 1),
            Err(Failure::InputBytes)
        ));
        // The key uses six bytes and the recovered scalar uses five. The syntax
        // view alone would count just three bytes for its folded value.
        budget_pair(input, |options| {
            options.budget.as_mut().unwrap().max_total_scalar_bytes = 10
        });
        let mut exact = options();
        exact.budget.as_mut().unwrap().max_total_scalar_bytes = 11;
        assert!(parse(input, exact, input.len()).is_ok());
        let padded = format!(
            "future: >-\n  {}\u{2028}  z\n#{}",
            "\\x".repeat(24),
            ".".repeat(128)
        );
        assert!(parse(&padded, options(), padded.len()).is_ok());
    }

    #[test]
    fn raw_c1_from_a_shipping_block_is_confined_to_that_scalar() {
        let saved = "future: >-\n  A\u{7f}\u{86}B\u{2028}  C\n";
        assert!(parse(saved, options(), MAX_TEXT_BYTES).is_ok());
        for doc in [
            format!("unknown: bad\u{86}\n{saved}"),
            format!("{saved}unknown: bad\u{7f}\n"),
            format!("{saved}# bad\u{86}\n"),
        ] {
            assert!(matches!(
                parse(&doc, options(), MAX_TEXT_BYTES),
                Err(Failure::InvalidYaml)
            ));
        }
    }

    #[test]
    fn extra_documents_tags_cycles_and_input_bearing_diagnostics_are_refused() {
        for input in [
            "{}\n---\n{}",
            "watch: {sources: [&cycle [*cycle]]}",
            "immich: {apiKey: !include synthetic}",
        ] {
            assert!(parse(input, options(), MAX_TEXT_BYTES).is_err());
        }
        let error = match parse(
            "immich: {allowInsecureHttp: SYNTHETIC-SECRET}",
            options(),
            MAX_TEXT_BYTES,
        ) {
            Ok(_) => panic!("invalid boolean accepted"),
            Err(error) => error,
        };
        assert!(!format!("{error:?} {error}").contains("SYNTHETIC-SECRET"));
    }
}
