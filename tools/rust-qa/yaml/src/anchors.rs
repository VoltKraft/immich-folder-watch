//! Match YamlDotNet's typed anchor bindings and flow mapping scalar handling.
use crate::codec::Failure;
use crate::scalar_breaks::Lines;
use serde_saphyr::granit_parser::{Event, Parser, StructureStyle};
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
    Text,
    Integer,
    Boolean,
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
            (Immich, "allowInsecureHttp")
            | (Source, "includeSubdirectories" | "deleteAfterUpload") => Boolean,
            (Watch, "batchIntervalSeconds" | "fileReadyTimeoutSeconds" | "maxBatchSize")
            | (Retry, "maxAttempts" | "baseDelayMilliseconds") => Integer,
            (Immich, "serverApiUrl" | "apiKey")
            | (Watch, "transferOrder")
            | (Source, "path" | "albumName" | "syncMode")
            | (Logging, "level" | "target" | "logDirectory")
            | (Localization, "language") => Text,
            _ => Skipped,
        }
    }

    fn element(self) -> Self {
        match self {
            Self::Sources => Self::Source,
            Self::Strings => Self::Text,
            _ => Self::Skipped,
        }
    }
}

enum Container {
    Sequence(Role),
    Mapping {
        role: Role,
        style: StructureStyle,
        next_value: Option<Role>,
    },
}

fn next_role(parent: Option<&mut Container>, key: Option<&str>) -> Role {
    match parent {
        None => Role::Config,
        Some(Container::Sequence(element)) => *element,
        Some(Container::Mapping {
            role, next_value, ..
        }) => {
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
    let has_alias_marker = input.contains('*');
    if !(has_alias_marker || input.contains('&') && input.contains('{')) {
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
    let mut expect_mapping_end = false;
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
            if expect_mapping_end && !matches!(event, Event::MappingEnd) {
                return Err(Failure::InvalidYaml);
            }
            expect_mapping_end = false;
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
                stack.push(if let Event::MappingStart(style, ..) = event {
                    Container::Mapping {
                        role: last_role,
                        style,
                        next_value: None,
                    }
                } else {
                    Container::Sequence(last_role.element())
                });
                continue;
            }
            Event::Scalar(value, _, anchor, _) => {
                // YamlDotNet 18.1 reads past the comma after an anchored scalar
                // value in a flow mapping. A trailing comma may precede its end.
                // An implicit empty value has no scalar token to read past.
                expect_mapping_end = anchor != 0
                    && !span.is_empty()
                    && matches!(
                        stack.last(),
                        Some(Container::Mapping {
                            style: StructureStyle::Flow,
                            next_value: Some(_),
                            ..
                        })
                    );
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
                if !has_alias_marker {
                    continue;
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

/// The high-level reader resolves core tags before delivering a scalar to Serde.
/// Keep the original scalar token and expose its resolved type to the property reader.
pub(super) fn typed_scalar_input<'a>(
    input: &'a str,
    options: &mut serde_saphyr::Options,
) -> Result<Cow<'a, str>, Failure> {
    let has_alias = input.contains('*') && input.contains('&');
    if !has_alias && !input.contains('!') {
        return Ok(Cow::Borrowed(input));
    }
    let lines = Lines::for_input(input);
    let syntax = lines.as_ref().map_or(input, |v| v.syntax.as_str());
    let original = |offset| lines.as_ref().map_or(offset, |v| v.original(offset));
    let mut stack = Vec::new();
    let mut tags = Vec::new();
    let mut implicit_anchor = None;
    let mut settings = crate::scalar_breaks::parser_options(options);
    settings.emit_anchor_events = true;
    for event in Parser::new_from_str_with_options(syntax, settings) {
        let (event, span) = event.map_err(|_| Failure::InvalidYaml)?;
        match event {
            Event::MappingStart(style, ..) | Event::SequenceStart(style, ..) => {
                if options
                    .budget
                    .as_ref()
                    .is_some_and(|b| stack.len() >= b.max_depth)
                {
                    return Err(Failure::Budget);
                }
                let role = next_role(stack.last_mut(), None);
                stack.push(if matches!(event, Event::MappingStart(..)) {
                    Container::Mapping {
                        role,
                        style,
                        next_value: None,
                    }
                } else {
                    Container::Sequence(role.element())
                });
            }
            Event::MappingEnd | Event::SequenceEnd => {
                stack.pop().ok_or(Failure::InvalidYaml)?;
            }
            Event::Scalar(value, _, anchor, tag) => {
                let property = match next_role(stack.last_mut(), Some(&value)) {
                    Role::Text => "text",
                    Role::Integer => "integer",
                    Role::Boolean => "boolean",
                    _ => continue,
                };
                if has_alias && anchor != 0 && tag.is_none() {
                    // The following Anchor event locates the name before any scalar
                    // style, including a block header or an implicit empty value.
                    implicit_anchor = Some((anchor, property));
                    continue;
                }
                let source = match tag.as_ref().and_then(|t| t.core_suffix()) {
                    Some("bool") => "bool",
                    Some("int") => "int",
                    Some("float") => "float",
                    // Preserve explicitly string-tagged null spellings verbatim.
                    // Reusing one as a non-string property already fails conversion.
                    Some("str")
                        if has_alias
                            && anchor != 0
                            && !matches!(value.as_ref(), "" | "~" | "null" | "Null" | "NULL") =>
                    {
                        "string"
                    }
                    _ => continue,
                };
                let span = span.tag_span().ok_or(Failure::InvalidYaml)?;
                let start = original(span.start.byte_offset().ok_or(Failure::InvalidYaml)?);
                let end = original(span.end.byte_offset().ok_or(Failure::InvalidYaml)?);
                tags.push((start, end, source, property));
            }
            Event::Anchor(id, _) => {
                if let Some((_, property)) = implicit_anchor.take_if(|(anchor, _)| *anchor == id) {
                    let offset = original(span.end.byte_offset().ok_or(Failure::InvalidYaml)?);
                    tags.push((offset, offset, "implicit", property));
                }
            }
            Event::Alias(_) | Event::UnresolvedAlias(_) => {
                next_role(stack.last_mut(), None);
            }
            _ => {}
        }
    }
    if tags.is_empty() {
        return Ok(Cow::Borrowed(input));
    }
    let mut checked = String::with_capacity(input.len());
    let mut typed = String::with_capacity(input.len());
    let mut copied = 0;
    for (start, end, source, property) in tags {
        let before = input.get(copied..start).ok_or(Failure::InvalidYaml)?;
        checked.push_str(before);
        typed.push_str(before);
        if start == end {
            typed.push(' ');
        } else {
            checked.push('!');
        }
        write!(typed, "!<{source}:{property}>").expect("writing to a string");
        copied = end;
    }
    checked.push_str(&input[copied..]);
    typed.push_str(&input[copied..]);
    // Admit the complete structure, original scalar contents, other tags and all
    // alias replays before reading the internally marked copy of this same document.
    let checked = crate::scalar_breaks::compatible_input(&checked, options)?;
    serde_saphyr::from_str_with_options::<serde::de::IgnoredAny>(&checked, options.clone())
        .map_err(crate::codec::classify)?;
    options.reject_unsupported_tags = false;
    Ok(Cow::Owned(typed))
}
