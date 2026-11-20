//! Legacy editing defaults and normalization, independent of filesystem authority.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
#[cfg(not(windows))]
use std::path::{Component, PathBuf};

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
pub struct RawConfig {
    immich: Option<RawImmich>,
    watch: Option<RawWatch>,
    retry: Option<RawRetry>,
    logging: Option<RawLogging>,
    localization: Option<RawLocalization>,
}

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct RawImmich {
    allow_insecure_http: Option<bool>,
    server_api_url: Option<String>,
    api_key: Option<String>,
}

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct RawWatch {
    sources: Option<Vec<Option<RawSource>>>,
    transfer_order: Option<String>,
    extensions: Option<Vec<Option<String>>>,
    #[serde(deserialize_with = "nullable_integer")]
    batch_interval_seconds: Option<i32>,
    #[serde(deserialize_with = "nullable_integer")]
    max_batch_size: Option<i32>,
    #[serde(deserialize_with = "nullable_integer")]
    file_ready_timeout_seconds: Option<i32>,
}

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct RawSource {
    path: Option<String>,
    album_name: Option<String>,
    include_subdirectories: Option<bool>,
    extensions: Option<Vec<Option<String>>>,
    exclude_directories: Option<Vec<Option<String>>>,
    exclude_file_names: Option<Vec<Option<String>>>,
    sync_mode: Option<String>,
    delete_after_upload: Option<bool>,
}

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct RawRetry {
    #[serde(deserialize_with = "nullable_integer")]
    max_attempts: Option<i32>,
    #[serde(deserialize_with = "nullable_integer")]
    base_delay_milliseconds: Option<i32>,
}

// YamlDotNet sets a present null non-nullable integer to zero; absent fields
// retain the class initializer. Option alone would collapse these two states.
fn nullable_integer<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> Result<Option<i32>, D::Error> {
    Option::<i32>::deserialize(deserializer).map(|value| Some(value.unwrap_or(0)))
}

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct RawLogging {
    level: Option<String>,
    target: Option<String>,
    log_directory: Option<String>,
}

#[derive(Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
struct RawLocalization {
    language: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Config {
    pub immich: Immich,
    pub watch: Watch,
    pub retry: Retry,
    pub logging: Logging,
    pub localization: Localization,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Immich {
    allow_insecure_http: bool,
    server_api_url: String,
    api_key: String,
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

    fn text(&self, value: Option<String>, default: &str) -> String {
        self.trim(value.as_deref().unwrap_or(default)).to_owned()
    }

    fn key(&self, value: &str) -> String {
        value
            .chars()
            .map(|value| self.ordinal.get(&value).copied().unwrap_or(value))
            .collect()
    }

    fn choice(&self, value: Option<String>, choices: &[&str], default: &str) -> String {
        let key = self.key(self.trim(value.as_deref().unwrap_or_default()));
        choices
            .iter()
            .find(|value| self.key(value) == key)
            .copied()
            .unwrap_or(default)
            .to_owned()
    }

    fn list(&self, values: Option<Vec<Option<String>>>, extensions: bool) -> Vec<String> {
        let mut seen = BTreeSet::new();
        values
            .unwrap_or_default()
            .into_iter()
            .flatten()
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
                    include_subdirectories: source.include_subdirectories.unwrap_or(false),
                    extensions: if extensions.is_empty() {
                        legacy.clone()
                    } else {
                        extensions
                    },
                    exclude_directories: rules.list(source.exclude_directories, false),
                    exclude_file_names: rules.list(source.exclude_file_names, false),
                    sync_mode: rules.choice(source.sync_mode, &["uploadAll", "sync"], "uploadNew"),
                    delete_after_upload: source.delete_after_upload.unwrap_or(false),
                }
            })
            .collect();
        let language = rules.text(localization.language, "auto");
        let log_directory = rules.text(logging.log_directory, "logs");
        Config {
            immich: Immich {
                allow_insecure_http: immich.allow_insecure_http.unwrap_or(false),
                server_api_url: rules.text(immich.server_api_url, ""),
                api_key: rules.text(immich.api_key, ""),
            },
            watch: Watch {
                sources,
                transfer_order: rules.choice(watch.transfer_order, &["oldestFirst"], "newestFirst"),
                extensions: Vec::new(),
                batch_interval_seconds: watch.batch_interval_seconds.unwrap_or(5),
                max_batch_size: watch.max_batch_size.unwrap_or(25),
                file_ready_timeout_seconds: watch.file_ready_timeout_seconds.unwrap_or(30),
            },
            retry: Retry {
                max_attempts: retry.max_attempts.unwrap_or(5),
                base_delay_milliseconds: retry.base_delay_milliseconds.unwrap_or(500),
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
