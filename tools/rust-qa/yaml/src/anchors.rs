//! YamlDotNet registers anchors only while deserializing a recognized value.
use crate::codec::Failure;
use crate::scalar_breaks::Lines;
use serde_saphyr::granit_parser::{Event, Parser};
use std::{borrow::Cow, collections::BTreeMap, fmt::Write};

#[derive(Clone, Copy, PartialEq, Eq)]
enum Role {
    Config,
    Immich,
    Watch,
    Sources,
    Source,
    Retry,
    Logging,
    Localization,
    Strings,
    Scalar,
    Key,
    Skipped,
}

impl Role {
    // These are the property names accepted by the shipping typed object reader.
    // Unknown subtrees remain in the input for syntax, tag, depth and replay checks.
    fn field(self, name: &str) -> Self {
        use Role::*;
        match (self, name) {
            (Config, "immich") => Immich,
            (Config, "watch") => Watch,
            (Config, "retry") => Retry,
            (Config, "logging") => Logging,
            (Config, "localization") => Localization,
            (Watch, "sources") => Sources,
            (Watch | Source, "extensions")
            | (Source, "excludeDirectories" | "excludeFileNames") => Strings,
            (Immich, "allowInsecureHttp" | "serverApiUrl" | "apiKey")
            | (
                Watch,
                "batchIntervalSeconds"
                | "fileReadyTimeoutSeconds"
                | "maxBatchSize"
                | "transferOrder",
            )
            | (
                Source,
                "path" | "albumName" | "includeSubdirectories" | "syncMode" | "deleteAfterUpload",
            )
            | (Retry, "maxAttempts" | "baseDelayMilliseconds")
            | (Logging, "level" | "target" | "logDirectory")
            | (Localization, "language") => Scalar,
            _ => Skipped,
        }
    }

    fn element(self) -> Self {
        match self {
            Self::Sources => Self::Source,
            Self::Strings => Self::Scalar,
            _ => Self::Skipped,
        }
    }
}

enum Container {
    Sequence(Role),
    Mapping {
        role: Role,
        next_value: Option<Role>,
    },
}

fn next_role(parent: Option<&mut Container>, key: Option<&str>) -> Role {
    match parent {
        None => Role::Config,
        Some(Container::Sequence(element)) => *element,
        Some(Container::Mapping { role, next_value }) => {
            if let Some(value) = next_value.take() {
                value
            } else {
                *next_value = Some(key.map_or(Role::Skipped, |name| role.field(name)));
                if *role == Role::Skipped {
                    Role::Skipped
                } else {
                    Role::Key
                }
            }
        }
    }
}

pub fn compatible_input<'a>(
    input: &'a str,
    options: &mut serde_saphyr::Options,
) -> Result<Cow<'a, str>, Failure> {
    if !input.contains('*') {
        return Ok(Cow::Borrowed(input));
    }
    // Interpret marker positions in the same physical lines as the shipping reader,
    // and edit only the marker bytes in the original decoded input.
    let lines = Lines::for_input(input);
    let syntax = lines.as_ref().map_or(input, |v| v.syntax.as_str());
    let original = |offset| lines.as_ref().map_or(offset, |v| v.original(offset));
    let mut settings = crate::scalar_breaks::parser_options(options);
    settings.emit_anchor_events = true;
    settings.emit_unresolved_aliases = true;

    let mut visible = BTreeMap::new();
    let mut stack = Vec::new();
    let mut last_role = Role::Skipped;
    let mut output = String::new();
    let mut copied = 0;
    let mut data_events = 0;
    let mut aliases = 0;
    let mut unresolved_skipped = 0;
    let mut anchors = 0;
    for event in Parser::new_from_str_with_options(syntax, settings) {
        let (event, span) = event.map_err(|_| Failure::InvalidYaml)?;
        // Bound the structural pass before the downstream reader checks the complete
        // stream, including document framing and expansion of every resolved alias.
        if matches!(
            event,
            Event::MappingStart(..)
                | Event::SequenceStart(..)
                | Event::Scalar(..)
                | Event::MappingEnd
                | Event::SequenceEnd
                | Event::Alias(_)
                | Event::UnresolvedAlias(_)
        ) {
            data_events += 1;
            if options
                .budget
                .as_ref()
                .is_some_and(|b| data_events > b.max_events)
            {
                return Err(Failure::Budget);
            }
        }
        let marker = match event {
            Event::DocumentStart(..) => {
                visible.clear();
                continue;
            }
            Event::MappingStart(..) | Event::SequenceStart(..) => {
                last_role = next_role(stack.last_mut(), None);
                if options
                    .budget
                    .as_ref()
                    .is_some_and(|b| stack.len() >= b.max_depth)
                {
                    return Err(Failure::Budget);
                }
                stack.push(if matches!(event, Event::MappingStart(..)) {
                    Container::Mapping {
                        role: last_role,
                        next_value: None,
                    }
                } else {
                    Container::Sequence(last_role.element())
                });
                continue;
            }
            Event::Scalar(value, ..) => {
                last_role = next_role(stack.last_mut(), Some(&value));
                continue;
            }
            Event::MappingEnd | Event::SequenceEnd => {
                stack.pop().ok_or(Failure::InvalidYaml)?;
                continue;
            }
            Event::Anchor(id, name) => {
                anchors += 1;
                if options
                    .budget
                    .as_ref()
                    .is_some_and(|b| anchors > b.max_anchors)
                {
                    return Err(Failure::Budget);
                }
                if !matches!(last_role, Role::Key | Role::Skipped) {
                    visible.insert(name.into_owned(), id);
                }
                Some(('&', id))
            }
            Event::Alias(_) | Event::UnresolvedAlias(_) => {
                aliases += 1;
                if options
                    .budget
                    .as_ref()
                    .is_some_and(|b| aliases > b.max_aliases)
                {
                    return Err(Failure::Budget);
                }
                let role = next_role(stack.last_mut(), None);
                match (role, event) {
                    // Preserve even ignored *resolved* replays for native work limits.
                    (Role::Skipped, Event::Alias(id)) => Some(('*', id)),
                    (Role::Skipped, Event::UnresolvedAlias(_)) => {
                        unresolved_skipped += 1;
                        None
                    }
                    (Role::Key, _) => return Err(Failure::InvalidYaml),
                    _ => {
                        let name = span
                            .slice(syntax)
                            .and_then(|text| text.strip_prefix('*'))
                            .ok_or(Failure::InvalidYaml)?;
                        Some(('*', *visible.get(name).ok_or(Failure::InvalidYaml)?))
                    }
                }
            }
            _ => continue,
        };
        let start = original(span.start.byte_offset().ok_or(Failure::InvalidYaml)?);
        let end = original(span.end.byte_offset().ok_or(Failure::InvalidYaml)?);
        output.push_str(input.get(copied..start).ok_or(Failure::InvalidYaml)?);
        if let Some((sigil, id)) = marker {
            write!(output, "{sigil}{id}").expect("writing to a string");
        } else {
            // An unbound reference inside skipped data has no target to replay.
            output.push_str("''");
        }
        copied = end;
    }
    if copied == 0 {
        return Ok(Cow::Borrowed(input));
    }
    if let Some(budget) = options.budget.as_mut() {
        if unresolved_skipped > 0
            && budget.enforce_alias_anchor_ratio
            && aliases >= budget.alias_anchor_min_aliases
            && (anchors == 0
                || aliases > budget.alias_anchor_ratio_multiplier.saturating_mul(anchors))
        {
            return Err(Failure::Budget);
        }
        budget.max_aliases -= unresolved_skipped;
    }
    output.push_str(input.get(copied..).ok_or(Failure::InvalidYaml)?);
    Ok(Cow::Owned(output))
}
