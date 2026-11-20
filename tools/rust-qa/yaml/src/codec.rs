//! Real serde-saphyr parsing with explicit bounded input, work and output.

use crate::model::{Config, RawConfig};
use serde_json::Value;
use serde_saphyr::{DuplicateKeyPolicy, MergeKeyPolicy, Options};
use std::io::Write;

pub const MAX_BYTES: usize = 65_536;

#[derive(Debug, PartialEq, Eq)]
pub enum Failure {
    InputBytes,
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
            max_reader_input_bytes: Some(MAX_BYTES), max_depth: 16, flow_nesting_limit: 16,
            max_nodes: 2048, max_events: 4096, max_documents: 1,
            max_total_scalar_bytes: 32_768, max_aliases: 32, max_anchors: 32,
            max_recorded_anchor_events: 4096, max_recorded_anchor_bytes: 65_536,
            max_inclusion_depth: 0,
        },
        duplicate_keys: DuplicateKeyPolicy::LastWins,
        merge_keys: MergeKeyPolicy::AsOrdinary,
        reject_unsupported_tags: true,
        strict_booleans: false,
        legacy_octal_numbers: true,
        with_snippet: false,
    };
    options.alias_limits.max_total_replayed_events = 4096;
    options.alias_limits.max_replay_stack_depth = 16;
    options.alias_limits.max_alias_expansions_per_anchor = 32;
    options
}

fn classify(error: serde_saphyr::Error) -> Failure {
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

pub fn parse(input: &str, options: Options, max_bytes: usize) -> Result<RawConfig, Failure> {
    if input.len() > max_bytes {
        return Err(Failure::InputBytes);
    }
    serde_saphyr::from_str_with_options::<Option<RawConfig>>(input, options)
        .map_err(classify)?
        .ok_or(Failure::InvalidDocument)
}

pub fn write(config: &Config) -> Result<Vec<u8>, Failure> {
    let mut value = serde_json::to_value(config).map_err(|_| Failure::InvalidDocument)?;
    value["watch"]
        .as_object_mut()
        .ok_or(Failure::InvalidDocument)?
        .remove("extensions");
    write_value(&value, MAX_BYTES)
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
        assert!(parse(input, options(), MAX_BYTES).is_ok());
        let mut limited = options();
        restrict(&mut limited);
        assert!(matches!(
            parse(input, limited, MAX_BYTES),
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
        let encoded = write_value(&value, MAX_BYTES).unwrap();
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
    fn extra_documents_tags_cycles_and_input_bearing_diagnostics_are_refused() {
        for input in [
            "{}\n---\n{}",
            "watch: {sources: [&cycle [*cycle]]}",
            "immich: {apiKey: !include synthetic}",
        ] {
            assert!(parse(input, options(), MAX_BYTES).is_err());
        }
        let error = match parse(
            "immich: {allowInsecureHttp: SYNTHETIC-SECRET}",
            options(),
            MAX_BYTES,
        ) {
            Ok(_) => panic!("invalid boolean accepted"),
            Err(error) => error,
        };
        assert!(!format!("{error:?} {error}").contains("SYNTHETIC-SECRET"));
    }
}
