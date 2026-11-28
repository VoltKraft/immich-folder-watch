//! Legacy editing defaults and normalization, independent of filesystem authority.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::path::Path;
#[cfg(not(windows))]
use std::path::{Component, PathBuf};

// The shipping typed reader assigns each occurrence as it reads it. An earlier
// malformed value still fails even when a later property would replace it.
macro_rules! legacy_mapping {
    ($visibility:vis struct $name:ident { $( $field:ident : $ty:ty => $key:literal ),* $(,)? }) => {
        #[derive(Default)]
        $visibility struct $name {
            $($field: $ty,)*
        }

        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
                struct Properties;
                impl<'de> serde::de::Visitor<'de> for Properties {
                    type Value = $name;

                    fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                        formatter.write_str("a configuration mapping")
                    }

                    fn visit_map<A: serde::de::MapAccess<'de>>(self, mut map: A) -> Result<$name, A::Error> {
                        let mut section = $name::default();
                        while let Some(key) = map.next_key::<String>()? {
                            match key.as_str() {
                                $($key => section.$field = map.next_value()?,)*
                                _ => { map.next_value::<serde::de::IgnoredAny>()?; }
                            }
                        }
                        Ok(section)
                    }
                }

                deserializer.deserialize_map(Properties)
            }
        }
    };
}

legacy_mapping! {
    pub struct RawConfig {
        immich: Option<RawImmich> => "immich",
        watch: Option<RawWatch> => "watch",
        retry: Option<RawRetry> => "retry",
        logging: Option<RawLogging> => "logging",
        localization: Option<RawLocalization> => "localization",
    }
}

legacy_mapping! {
    struct RawImmich {
        allow_insecure_http: RawFlag => "allowInsecureHttp",
        server_api_url: RawText => "serverApiUrl",
        api_key: RawText => "apiKey",
    }
}

legacy_mapping! {
    struct RawWatch {
        sources: Option<Vec<Option<RawSource>>> => "sources",
        transfer_order: RawText => "transferOrder",
        extensions: Option<Vec<RawText>> => "extensions",
        batch_interval_seconds: RawInteger => "batchIntervalSeconds",
        max_batch_size: RawInteger => "maxBatchSize",
        file_ready_timeout_seconds: RawInteger => "fileReadyTimeoutSeconds",
    }
}

legacy_mapping! {
    struct RawSource {
        path: RawText => "path",
        album_name: RawText => "albumName",
        include_subdirectories: RawFlag => "includeSubdirectories",
        extensions: Option<Vec<RawText>> => "extensions",
        exclude_directories: Option<Vec<RawText>> => "excludeDirectories",
        exclude_file_names: Option<Vec<RawText>> => "excludeFileNames",
        sync_mode: RawText => "syncMode",
        delete_after_upload: RawFlag => "deleteAfterUpload",
    }
}

legacy_mapping! {
    struct RawRetry {
        max_attempts: RawInteger => "maxAttempts",
        base_delay_milliseconds: RawInteger => "baseDelayMilliseconds",
    }
}

// Direct string deserialization retains the spelling of untagged scalar values.
// The structural reader has already validated the document before marking a
// recognized property's explicit numeric or Boolean tag.
enum Scalar {
    Null,
    Text(String, bool),
    Int(i32),
    Bool(bool),
    Float(f64),
    Other(String),
}

impl Scalar {
    fn read<'de, D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let serde_saphyr::Tagged(value, tag) =
            serde_saphyr::Tagged::<Option<String>>::deserialize(deserializer)?;
        let invalid = || serde::de::Error::custom("invalid configuration scalar");
        // An alias replays the value assigned to its defining property. An
        // integer stored in an album name therefore reaches later uses as text.
        if let Some((kind @ ("bool" | "int" | "float"), property)) =
            tag.as_deref().and_then(|t| t.split_once(':'))
        {
            let text = value.ok_or_else(invalid)?;
            let typed = match kind {
                "int" => legacy_integer(&text).map(Self::Int),
                "bool" => legacy_flag(&text, false).map(Self::Bool),
                _ => text.trim().parse().ok().map(Self::Float),
            }
            .ok_or_else(invalid)?;
            return match property {
                "text" => Ok(Self::Text(typed.text().ok_or_else(invalid)?, true)),
                "integer" => typed.integer().map(Self::Int).ok_or_else(invalid),
                "boolean" => typed.flag().map(Self::Bool).ok_or_else(invalid),
                _ => Err(invalid()),
            };
        }
        Ok(match (tag.as_deref(), value) {
            (_, None) => Self::Null,
            (Some("tag:yaml.org,2002:str"), Some(text)) => Self::Text(text, true),
            (None | Some("!"), Some(text)) => Self::Text(text, false),
            (_, Some(text)) => Self::Other(text),
        })
    }

    fn text(self) -> Option<String> {
        match self {
            Self::Null => None,
            Self::Text(text, _) | Self::Other(text) => Some(text),
            Self::Int(number) => Some(number.to_string()),
            Self::Bool(value) => Some(if value { "True" } else { "False" }.into()),
            Self::Float(value) => Some(float_text(value)),
        }
    }

    fn integer(self) -> Option<i32> {
        match self {
            Self::Null => Some(0),
            Self::Int(value) => Some(value),
            Self::Bool(value) => Some(i32::from(value)),
            Self::Text(text, true) => text.trim().parse().ok(),
            Self::Text(text, false) => legacy_integer(&text),
            Self::Float(value) => {
                let rounded = value.round_ties_even();
                (f64::from(i32::MIN)..=f64::from(i32::MAX))
                    .contains(&rounded)
                    .then_some(rounded as i32)
            }
            Self::Other(_) => None,
        }
    }

    fn flag(self) -> Option<bool> {
        match self {
            Self::Null => Some(false),
            Self::Bool(value) => Some(value),
            Self::Int(value) => Some(value != 0),
            Self::Float(value) => Some(value != 0.0),
            Self::Text(text, tagged_string) => legacy_flag(&text, tagged_string),
            Self::Other(_) => None,
        }
    }
}

#[derive(Default)]
struct RawText(Option<String>);

impl<'de> Deserialize<'de> for RawText {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        Ok(Self(Scalar::read(deserializer)?.text()))
    }
}

// .NET 10 general-format Double uses shortest round-trip digits and switches
// to an uppercase, signed exponent outside its fixed-point range.
fn float_text(value: f64) -> String {
    if value.is_nan() {
        return "NaN".to_owned();
    }
    if value.is_infinite() {
        return if value.is_sign_negative() {
            "-Infinity"
        } else {
            "Infinity"
        }
        .to_owned();
    }
    let scientific = format!("{value:e}");
    let (mantissa, exponent) = scientific.split_once('e').expect("finite float exponent");
    let exponent: i32 = exponent.parse().expect("formatted exponent");
    if (-4..17).contains(&exponent) {
        value.to_string()
    } else {
        format!("{mantissa}E{exponent:+03}")
    }
}

// A missing integer keeps its C# class initializer. An explicit null assigns zero.
#[derive(Default)]
struct RawInteger(Option<i32>);

fn legacy_integer(text: &str) -> Option<i32> {
    let (negative, digits) = match text.as_bytes().first() {
        Some(b'-') => (true, &text[1..]),
        Some(b'+') => (false, &text[1..]),
        _ => (false, text),
    };
    let magnitude = if digits.starts_with('0') && digits.len() > 1 {
        let (radix, suffix) = match digits.as_bytes()[1] {
            b'b' => (2, &digits[2..]),
            b'x' => (16, &digits[2..]),
            _ => (8, &digits[1..]),
        };
        u64::from_str_radix(&suffix.replace('_', ""), radix).ok()?
    } else {
        // YamlDotNet treats each following decimal component as a base-60 digit.
        let mut number = 0u64;
        for (i, component) in digits.split(':').enumerate() {
            let part = component.replace('_', "");
            let part = part.trim_ascii().parse::<u64>().ok()?;
            if i != 0 && part >= 60 {
                return None;
            }
            number = number.checked_mul(60)?.checked_add(part)?;
        }
        number
    };
    let number = i64::try_from(magnitude).ok()?;
    i32::try_from(if negative { -number } else { number }).ok()
}

impl<'de> Deserialize<'de> for RawInteger {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let number = Scalar::read(deserializer)?.integer();
        number
            .map(|n| Self(Some(n)))
            .ok_or_else(|| serde::de::Error::custom("invalid legacy configuration integer"))
    }
}

fn legacy_flag(text: &str, tagged_string: bool) -> Option<bool> {
    let value = if tagged_string {
        text.trim()
    } else {
        text.strip_suffix('\n').unwrap_or(text)
    };
    match (value.to_ascii_lowercase().as_str(), tagged_string) {
        ("true", _) | ("y" | "yes" | "on", false) => Some(true),
        ("false", _) | ("n" | "no" | "off", false) => Some(false),
        _ => None,
    }
}

#[derive(Default)]
struct RawFlag(bool);

impl<'de> Deserialize<'de> for RawFlag {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let value = Scalar::read(deserializer)?.flag();
        value
            .map(Self)
            .ok_or_else(|| serde::de::Error::custom("invalid legacy configuration boolean"))
    }
}

legacy_mapping! {
    struct RawLogging {
        level: RawText => "level",
        target: RawText => "target",
        log_directory: RawText => "logDirectory",
    }
}

legacy_mapping! {
    struct RawLocalization {
        language: RawText => "language",
    }
}

#[derive(Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Config {
    pub immich: Immich,
    pub watch: Watch,
    pub retry: Retry,
    pub logging: Logging,
    pub localization: Localization,
}

impl fmt::Debug for Config {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("Config")
            .field("source_count", &self.watch.sources.len())
            .finish_non_exhaustive()
    }
}

#[derive(Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Immich {
    allow_insecure_http: bool,
    server_api_url: String,
    api_key: String,
}

impl fmt::Debug for Immich {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("Immich")
            .field("allow_insecure_http", &self.allow_insecure_http)
            .finish_non_exhaustive()
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Watch {
    pub sources: Vec<Source>,
    transfer_order: String,
    extensions: Vec<String>,
    batch_interval_seconds: i32,
    max_batch_size: i32,
    file_ready_timeout_seconds: i32,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Source {
    pub path: String,
    album_name: String,
    include_subdirectories: bool,
    extensions: Vec<String>,
    exclude_directories: Vec<String>,
    exclude_file_names: Vec<String>,
    sync_mode: String,
    delete_after_upload: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Retry {
    pub max_attempts: i32,
    base_delay_milliseconds: i32,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Logging {
    level: String,
    target: String,
    pub log_directory: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Localization {
    pub language: String,
}

/// Per-run development reference only: no universal casing table is embedded.
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Casing {
    pub scalars: usize,
    pub context_batches: usize,
    lower: Vec<(u32, u32)>,
    ordinal: Vec<(u32, u32)>,
    whitespace: Vec<u32>,
}

pub struct TextRules {
    lower: BTreeMap<char, char>,
    ordinal: BTreeMap<char, char>,
    whitespace: BTreeSet<char>,
}

impl TextRules {
    pub fn from_reference(reference: Casing) -> Result<Self, &'static str> {
        fn map(pairs: Vec<(u32, u32)>) -> Result<BTreeMap<char, char>, &'static str> {
            if pairs.len() > 10_000 || pairs.windows(2).any(|pair| pair[0].0 >= pair[1].0) {
                return Err("invalid native casing reference order");
            }
            pairs
                .into_iter()
                .map(|(from, to)| {
                    Ok((
                        char::from_u32(from).ok_or("invalid casing scalar")?,
                        char::from_u32(to).ok_or("invalid casing scalar")?,
                    ))
                })
                .collect()
        }
        if reference.scalars != 1_112_064 || reference.context_batches != 272 {
            return Err("incomplete native string-operation reference");
        }
        Ok(Self {
            lower: map(reference.lower)?,
            ordinal: map(reference.ordinal)?,
            whitespace: reference
                .whitespace
                .into_iter()
                .map(|value| char::from_u32(value).ok_or("invalid trim scalar"))
                .collect::<Result<_, _>>()?,
        })
    }

    fn trim<'a>(&self, value: &'a str) -> &'a str {
        value.trim_matches(|value| self.whitespace.contains(&value))
    }

    fn text(&self, value: RawText, default: &str) -> String {
        self.trim(value.0.as_deref().unwrap_or(default)).to_owned()
    }

    fn key(&self, value: &str) -> String {
        value
            .chars()
            .map(|value| self.ordinal.get(&value).copied().unwrap_or(value))
            .collect()
    }

    fn choice(&self, value: RawText, choices: &[&str], default: &str) -> String {
        let key = self.key(self.trim(value.0.as_deref().unwrap_or_default()));
        choices
            .iter()
            .find(|value| self.key(value) == key)
            .copied()
            .unwrap_or(default)
            .to_owned()
    }

    fn list(&self, values: Option<Vec<RawText>>, extensions: bool) -> Vec<String> {
        let mut seen = BTreeSet::new();
        values
            .unwrap_or_default()
            .into_iter()
            .filter_map(|item| item.0)
            .filter_map(|value| {
                let value = self.trim(&value);
                if value.is_empty() {
                    return None;
                }
                let mut normalized: String = if extensions {
                    value
                        .chars()
                        .map(|value| self.lower.get(&value).copied().unwrap_or(value))
                        .collect()
                } else {
                    value.to_owned()
                };
                if extensions && !normalized.starts_with('.') {
                    normalized.insert(0, '.');
                }
                seen.insert(self.key(&normalized)).then_some(normalized)
            })
            .collect()
    }
}

impl RawConfig {
    #[cfg(target_os = "linux")]
    pub(crate) fn startup_language(self) -> Option<String> {
        self.localization.and_then(|settings| settings.language.0)
    }

    pub fn normalize(self, rules: &TextRules) -> Config {
        let immich = self.immich.unwrap_or_default();
        let watch = self.watch.unwrap_or_default();
        let retry = self.retry.unwrap_or_default();
        let logging = self.logging.unwrap_or_default();
        let localization = self.localization.unwrap_or_default();
        let legacy = rules.list(watch.extensions, true);
        let sources = watch
            .sources
            .unwrap_or_default()
            .into_iter()
            .flatten()
            .map(|source| {
                let extensions = rules.list(source.extensions, true);
                Source {
                    path: rules.text(source.path, ""),
                    album_name: rules.text(source.album_name, ""),
                    include_subdirectories: source.include_subdirectories.0,
                    extensions: if extensions.is_empty() {
                        legacy.clone()
                    } else {
                        extensions
                    },
                    exclude_directories: rules.list(source.exclude_directories, false),
                    exclude_file_names: rules.list(source.exclude_file_names, false),
                    sync_mode: rules.choice(source.sync_mode, &["uploadAll", "sync"], "uploadNew"),
                    delete_after_upload: source.delete_after_upload.0,
                }
            })
            .collect();
        let language = rules.text(localization.language, "auto");
        let log_directory = rules.text(logging.log_directory, "logs");
        Config {
            immich: Immich {
                allow_insecure_http: immich.allow_insecure_http.0,
                server_api_url: rules.text(immich.server_api_url, ""),
                api_key: rules.text(immich.api_key, ""),
            },
            watch: Watch {
                sources,
                transfer_order: rules.choice(watch.transfer_order, &["oldestFirst"], "newestFirst"),
                extensions: Vec::new(),
                batch_interval_seconds: watch.batch_interval_seconds.0.unwrap_or(5),
                max_batch_size: watch.max_batch_size.0.unwrap_or(25),
                file_ready_timeout_seconds: watch.file_ready_timeout_seconds.0.unwrap_or(30),
            },
            retry: Retry {
                max_attempts: retry.max_attempts.0.unwrap_or(5),
                base_delay_milliseconds: retry.base_delay_milliseconds.0.unwrap_or(500),
            },
            logging: Logging {
                level: rules.text(logging.level, "Information"),
                target: rules.choice(
                    logging.target,
                    &["eventLog", "file", "journald"],
                    "eventLog",
                ),
                log_directory: if log_directory.is_empty() {
                    "logs".to_owned()
                } else {
                    log_directory
                },
            },
            localization: Localization {
                language: if language.is_empty() {
                    "auto".to_owned()
                } else {
                    language
                },
            },
        }
    }
}

impl Config {
    pub fn runtime(&self, profile: &Path) -> Result<Self, &'static str> {
        let mut result = self.clone();
        for source in &mut result.watch.sources {
            source.path = normalize_path(&source.path, profile)?;
        }
        result.logging.log_directory = normalize_path(&result.logging.log_directory, profile)?;
        Ok(result)
    }

    pub fn mutate(&mut self) {
        self.localization.language = "de".to_owned();
        self.retry.max_attempts = 9;
        self.watch.sources.push(Source {
            path: "Neu/../Fotos 日本語".to_owned(),
            album_name: "Rust – Grüße 日本語 😀: # null".to_owned(),
            include_subdirectories: true,
            extensions: vec![".heic".to_owned()],
            exclude_directories: Vec::new(),
            exclude_file_names: Vec::new(),
            sync_mode: "sync".to_owned(),
            delete_after_upload: false,
        });
    }
}

fn normalize_path(value: &str, profile: &Path) -> Result<String, &'static str> {
    if value.is_empty() {
        return Ok(String::new());
    }
    if value.contains('\0') || !profile.is_absolute() {
        return Err("unsupported configuration path");
    }
    let path = profile.join(value);
    if !path.is_absolute() {
        return Err("drive-relative configuration path is not qualified");
    }
    #[cfg(windows)]
    let result = std::path::absolute(&path).map_err(|_| "native configuration path failed")?;
    #[cfg(not(windows))]
    let result = {
        let mut result = PathBuf::from("/");
        for component in path.components() {
            match component {
                Component::Normal(value) => result.push(value),
                Component::ParentDir => {
                    result.pop();
                }
                Component::RootDir | Component::CurDir => {}
                Component::Prefix(_) => return Err("unsupported configuration path"),
            }
        }
        result
    };
    let mut result = result
        .into_os_string()
        .into_string()
        .map_err(|_| "non-Unicode configuration path")?;
    if (value.ends_with('/') || cfg!(windows) && value.ends_with('\\'))
        && !result.ends_with(std::path::MAIN_SEPARATOR)
    {
        result.push(std::path::MAIN_SEPARATOR);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn configuration_debug_omits_profile_values_but_serialization_preserves_them() {
        let config = serde_json::json!({
            "immich": {
                "allowInsecureHttp": false, "serverApiUrl": "https://endpoint.invalid/private",
                "apiKey": "synthetic-yaml-key"
            },
            "watch": {
                "sources": [], "extensions": [], "transferOrder": "newestFirst",
                "batchIntervalSeconds": 5, "maxBatchSize": 25, "fileReadyTimeoutSeconds": 30
            },
            "retry": {"maxAttempts": 5, "baseDelayMilliseconds": 500},
            "logging": {"level": "Information", "target": "file", "logDirectory": "synthetic-log-dir"},
            "localization": {"language": "auto"}
        });
        let model: Config = serde_json::from_value(config.clone()).unwrap();
        let diagnostics = format!(
            "{model:?} {model:#?} {:?} {:#?}",
            model.immich, model.immich
        );
        for value in [
            "synthetic-yaml-key",
            "endpoint.invalid",
            "synthetic-log-dir",
        ] {
            assert!(
                !diagnostics.contains(value),
                "profile value in Debug output"
            );
        }
        assert!(serde_json::to_value(model).unwrap() == config);
    }
}
