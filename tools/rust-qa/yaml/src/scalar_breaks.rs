//! Preserve the shipping scanner's physical Unicode breaks using its scalar styles and indentation.
use crate::codec::{Failure, classify};
use serde_saphyr::granit_parser::{self, ScalarStyle, Scanner, StrInput, TokenType};
use std::borrow::Cow;

const SEPARATORS: [char; 3] = ['\u{85}', '\u{2028}', '\u{2029}'];
const BREAKS: [char; 5] = ['\r', '\n', '\u{85}', '\u{2028}', '\u{2029}'];

// The 1.2 scanner recognizes LF/CR as syntax. Give it the physical line boundaries
// seen by YamlDotNet and map token byte positions back to the untouched decoded input.
// Scalar content is recovered from the original spelling before typed deserialization.
struct Lines {
    syntax: String,
    offsets: Vec<(usize, usize)>,
    block_controls: Vec<usize>,
}

impl Lines {
    fn new(original: &str) -> Self {
        let mut syntax = String::with_capacity(original.len());
        let mut offsets = Vec::new();
        let mut block_controls = Vec::new();
        for (offset, ch) in original.char_indices() {
            if SEPARATORS.contains(&ch) {
                syntax.push('\n');
                offsets.push((syntax.len(), offset + ch.len_utf8() - syntax.len()));
            } else if matches!(ch, '\u{7f}'..='\u{9f}') {
                // YamlDotNet can write DEL/C1 verbatim when it switches to a multiline block.
                // Keep columns and byte width. Only covered block contents may use this spelling.
                block_controls.push(syntax.len());
                syntax.push(if ch.is_ascii() { 'x' } else { 'é' });
            } else {
                syntax.push(ch);
            }
        }
        Self {
            syntax,
            offsets,
            block_controls,
        }
    }

    fn original(&self, index: usize) -> usize {
        let n = self.offsets.partition_point(|&(end, _)| end <= index);
        index + n.checked_sub(1).map_or(0, |i| self.offsets[i].1)
    }
}

pub fn compatible_input<'a>(
    input: &'a str,
    options: &serde_saphyr::Options,
) -> Result<Cow<'a, str>, Failure> {
    if !input.contains(SEPARATORS) {
        return Ok(Cow::Borrowed(input));
    }
    let lines = Lines::new(input);
    let syntax = lines.syntax.as_str();
    // Check nesting, node, alias and replay limits before inspecting individual token spans.
    serde_saphyr::from_str_with_options::<serde::de::IgnoredAny>(syntax, options.clone())
        .map_err(classify)?;
    // The admitted original is bounded at the codec entry. A generated YAML escape can
    // take up to six bytes per input byte, independently of the decoded scalar budget.
    let limit = 6 * input.len() + 2;
    let mut parser_options = granit_parser::options! {
        bom_inside_document_as_content: options.bom_inside_document_as_content,
        strict_indentation: options.strict_indentation,
    };
    if let Some(budget) = options.budget.as_ref() {
        parser_options.flow_nesting_limit = budget.flow_nesting_limit;
        parser_options.simple_key_max_lookahead = budget.simple_key_max_lookahead;
    }
    let mut output = String::new();
    let mut copied = 0;
    let mut previous = 0;
    let mut controls = lines.block_controls.as_slice();
    for token in Scanner::with_options(StrInput::new(syntax), parser_options) {
        let (span, kind) = token.map_err(|_| Failure::InvalidYaml)?.into_parts();
        let start = span.start.byte_offset().ok_or(Failure::InvalidYaml)?;
        let end = span.end.byte_offset().ok_or(Failure::InvalidYaml)?;
        let lower = previous.min(start);
        previous = previous.max(end);
        let TokenType::Scalar(style, decoded) = kind else {
            continue;
        };
        let is_block = matches!(style, ScalarStyle::Literal | ScalarStyle::Folded);
        let lo = if is_block { lower } else { start };
        let original = &input[lines.original(lo)..lines.original(end)];
        if !original.contains(SEPARATORS) {
            continue;
        }
        let (replace_at, value) = if is_block {
            // Nonempty block token spans start at content, after the header and first indent.
            let indicator = if style == ScalarStyle::Literal {
                '|'
            } else {
                '>'
            };
            let header = header_offset(syntax, lo, start, indicator)?;
            let header_end = syntax[header..end]
                .find(['\r', '\n'])
                .map_or(end, |n| header + n);
            let header_line = &syntax[header..header_end];
            let chomp = header_line[1..]
                .chars()
                .take_while(|ch| ch.is_ascii_digit() || matches!(ch, '+' | '-'))
                .find(|ch| matches!(ch, '+' | '-'));
            let mut first_line = header_end;
            if first_line < end {
                first_line += if syntax[first_line..end].starts_with("\r\n") {
                    2
                } else {
                    1
                };
            }
            let raw = &input[lines.original(first_line)..lines.original(end)];
            if !raw.contains(SEPARATORS) {
                continue;
            }
            if controls.first().is_some_and(|&index| index < first_line) {
                return Err(Failure::InvalidYaml);
            }
            controls = &controls[controls.partition_point(|&index| index < end)..];
            (
                header,
                block(
                    raw,
                    span.indent.unwrap_or(span.start.col()),
                    style == ScalarStyle::Folded,
                    chomp,
                )?,
            )
        } else {
            (start, flow(original, style)?)
        };
        if value == decoded {
            continue;
        }
        if copied > replace_at {
            return Err(Failure::InvalidYaml);
        }
        output.push_str(&syntax[copied..replace_at]);
        // The same YAML serializer used by the ordinary writer escapes DEL, C1 and Unicode
        // separators as needed. Its single quoted scalar has one terminating document LF.
        let quoted = serde_saphyr::to_string_with_options(
            &value,
            serde_saphyr::ser_options! { quote_all: true },
        )
        .map_err(|_| Failure::InvalidYaml)?;
        output.push_str(quoted.strip_suffix('\n').unwrap_or(&quoted));
        if is_block && end < syntax.len() {
            output.push('\n');
            output.extend(std::iter::repeat_n(' ', span.end.col()));
        }
        if output.len() > limit {
            return Err(Failure::InputBytes);
        }
        copied = end;
    }
    if !controls.is_empty() {
        return Err(Failure::InvalidYaml);
    }
    if copied == 0 {
        return Ok(Cow::Owned(lines.syntax));
    }
    if syntax.len() - copied > limit.saturating_sub(output.len()) {
        return Err(Failure::InputBytes);
    }
    output.push_str(&syntax[copied..]);
    Ok(Cow::Owned(output))
}

fn header_offset(syntax: &str, lo: usize, start: usize, indicator: char) -> Result<usize, Failure> {
    // The scanner has consumed any preceding anchor, tag and key. Ignore intervening comments.
    let mut comment = false;
    for (n, ch) in syntax[lo..]
        .char_indices()
        .take_while(|(n, _)| lo + n <= start)
    {
        match ch {
            '\r' | '\n' => comment = false,
            '#' => comment = true,
            _ if !comment && ch == indicator => return Ok(lo + n),
            _ => {}
        }
    }
    Err(Failure::InvalidYaml)
}

fn block(
    mut body: &str,
    indent: usize,
    folded: bool,
    chomp: Option<char>,
) -> Result<String, Failure> {
    let mut value = String::with_capacity(body.len());
    let mut breaks = String::new();
    let mut previous_indented = false;
    let mut has_content = false;
    while !body.is_empty() {
        let next = body.find(BREAKS).unwrap_or(body.len());
        let (line, rest) = body.split_at(next);
        let spaces = line.len() - line.trim_start_matches(' ').len();
        if spaces < indent && spaces != line.len() {
            return Err(Failure::InvalidYaml);
        }
        let content = &line[spaces.min(indent)..];
        if !content.is_empty() {
            let indented = content.starts_with([' ', '\t']);
            if has_content
                && folded
                && !previous_indented
                && !indented
                && let Some(tail) = breaks.strip_prefix('\n')
            {
                value.push_str(if tail.is_empty() { " " } else { tail });
            } else {
                value.push_str(&breaks);
            }
            breaks.clear();
            value.push_str(content);
            previous_indented = indented;
            has_content = true;
        }
        let Some(ch) = rest.chars().next() else { break };
        breaks.push(normalized_break(ch));
        body = skip_break(rest, ch);
    }
    match chomp {
        Some('+') => value.push_str(&breaks),
        None if has_content => value.extend(breaks.chars().take(1)),
        _ => {}
    }
    Ok(value)
}

fn normalized_break(ch: char) -> char {
    if matches!(ch, '\r' | '\u{85}') {
        '\n'
    } else {
        ch
    }
}

fn skip_break(rest: &str, ch: char) -> &str {
    rest.strip_prefix("\r\n").unwrap_or(&rest[ch.len_utf8()..])
}

fn flow(raw: &str, style: ScalarStyle) -> Result<String, Failure> {
    let double = style == ScalarStyle::DoubleQuoted;
    let mut body = match style {
        ScalarStyle::SingleQuoted | ScalarStyle::DoubleQuoted => raw
            .get(1..raw.len().saturating_sub(1))
            .ok_or(Failure::InvalidYaml)?,
        ScalarStyle::Plain => raw,
        _ => return Err(Failure::InvalidYaml),
    };
    let mut value = String::with_capacity(raw.len());
    if double {
        value.push('"');
    }
    while let Some(ch) = body.chars().next() {
        if double && ch == '\\' {
            let escape = &body[1..];
            let next = escape.chars().next().ok_or(Failure::InvalidYaml)?;
            if BREAKS.contains(&next) {
                body = append_flow_space(skip_break(escape, next), &mut value, true, true);
            } else {
                value.push('\\');
                value.push(next);
                body = &escape[next.len_utf8()..];
            }
        } else if ch == '\'' && style == ScalarStyle::SingleQuoted {
            body = body.strip_prefix("''").ok_or(Failure::InvalidYaml)?;
            value.push('\'');
        } else if BREAKS.contains(&ch) || matches!(ch, ' ' | '\t') {
            body = append_flow_space(body, &mut value, double, false);
        } else {
            value.push(ch);
            body = &body[ch.len_utf8()..];
        }
    }
    if double {
        value.push('"');
        // Decode ordinary YAML escape sequences in their original quoted context.
        serde_saphyr::from_str_with_options(&value, crate::codec::options())
            .map_err(|_| Failure::InvalidYaml)
    } else {
        Ok(value)
    }
}

fn append_flow_space<'a>(
    mut body: &'a str,
    value: &mut String,
    double: bool,
    escaped: bool,
) -> &'a str {
    let original = body;
    let mut breaks = String::new();
    while let Some(ch) = body.chars().next() {
        if BREAKS.contains(&ch) {
            breaks.push(normalized_break(ch));
            body = skip_break(body, ch);
        } else if matches!(ch, ' ' | '\t') {
            body = &body[1..];
        } else {
            break;
        }
    }
    if breaks.is_empty() && !escaped {
        value.push_str(&original[..original.len() - body.len()]);
        return body;
    }
    let retained = if !escaped && let Some(rest) = breaks.strip_prefix('\n') {
        if rest.is_empty() { " " } else { rest }
    } else {
        &breaks
    };
    for ch in retained.chars() {
        match (double, ch) {
            (true, '\u{2028}') => value.push_str("\\L"),
            (true, '\u{2029}') => value.push_str("\\P"),
            (true, '\n') => value.push_str("\\n"),
            _ => value.push(ch),
        }
    }
    body
}
