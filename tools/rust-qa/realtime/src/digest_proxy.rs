//! Digest authentication of the selected Linux HTTP proxy for one CONNECT retry.
use md5::{Digest, Md5};
use percent_encoding::percent_decode_str;
use reqwest::{Url, header};
use sha2::Sha256;
use std::collections::{BTreeMap, VecDeque};
use std::fmt::Write;
use std::sync::Mutex;

use crate::Error;

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum Algorithm {
    Md5,
    Sha256,
}

impl Algorithm {
    fn hash(self, value: &str) -> String {
        fn hex(bytes: &[u8]) -> String {
            let mut result = String::with_capacity(bytes.len() * 2);
            for byte in bytes {
                write!(result, "{byte:02x}").expect("writing to a String");
            }
            result
        }
        match self {
            Self::Md5 => hex(&Md5::digest(value)),
            Self::Sha256 => hex(&Sha256::digest(value)),
        }
    }

    fn name(self) -> &'static str {
        match self {
            Self::Md5 => "MD5",
            Self::Sha256 => "SHA-256",
        }
    }
}

type Fields = BTreeMap<String, String>;

// Multiple requests may be challenged concurrently by the same configured proxy.
#[derive(Default)]
pub(super) struct DigestState {
    recent: Mutex<VecDeque<NonceUse>>,
}

struct NonceUse {
    server: [u8; 32],
    client: u128,
    count: u32,
}

impl DigestState {
    fn next(&self, nonce: &str) -> Result<(String, u32), Error> {
        // Keep recent server nonces across rotations and bound the per-proxy storage.
        const CAPACITY: usize = 32;
        let server = Sha256::digest(nonce).into();
        let mut recent = self.recent.lock().map_err(|_| Error::Protocol)?;
        let entry = if let Some(index) = recent.iter().position(|entry| entry.server == server) {
            let count = recent[index].count.checked_add(1).ok_or(Error::Protocol)?;
            let mut entry = recent.remove(index).ok_or(Error::Protocol)?;
            entry.count = count;
            entry
        } else {
            let mut random = [0; 16];
            rustls::crypto::ring::default_provider()
                .secure_random
                .fill(&mut random)
                .map_err(|_| Error::Protocol)?;
            if recent.len() == CAPACITY {
                recent.pop_front();
            }
            NonceUse {
                server,
                client: u128::from_be_bytes(random),
                count: 1,
            }
        };
        let used = (format!("{:032x}", entry.client), entry.count);
        recent.push_back(entry);
        Ok(used)
    }
}

struct Challenge {
    fields: Fields,
    algorithm: Algorithm,
    session: bool,
    qop: Option<&'static str>,
}

fn quoted(value: &str) -> String {
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

fn unquote(value: &str) -> Option<String> {
    if !value.starts_with('"') {
        return (!value.is_empty() && value.bytes().all(token)).then(|| value.to_owned());
    }
    let mut chars = value.strip_prefix('"')?.strip_suffix('"')?.chars();
    let mut result = String::new();
    while let Some(c) = chars.next() {
        match c {
            '\\' => result.push(chars.next()?),
            '"' => return None,
            _ => result.push(c),
        }
    }
    Some(result)
}

fn token(c: u8) -> bool {
    c.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&c)
}

fn insert(fields: &mut Fields, key_value: &str) -> Option<()> {
    let (key, value) = key_value.split_once('=')?;
    let key = key.trim();
    if key.is_empty() || !key.bytes().all(token) {
        return None;
    }
    fields
        .insert(key.to_ascii_lowercase(), unquote(value.trim())?)
        .is_none()
        .then_some(())
}

impl Challenge {
    fn parse(fields: Fields) -> Option<Self> {
        let name = fields
            .get("algorithm")
            .map_or("MD5", String::as_str)
            .to_ascii_uppercase();
        let session = name.ends_with("-SESS");
        let algorithm = match name.strip_suffix("-SESS").unwrap_or(&name) {
            "MD5" => Algorithm::Md5,
            "SHA-256" => Algorithm::Sha256,
            _ => return None,
        };
        fields.get("realm")?;
        if fields.get("nonce")?.is_empty()
            || fields
                .get("charset")
                .is_some_and(|s| !s.eq_ignore_ascii_case("UTF-8"))
            || fields.get("userhash").is_some_and(|s| {
                !s.eq_ignore_ascii_case("false") && !s.eq_ignore_ascii_case("true")
            })
        {
            return None;
        }
        let qop = match fields.get("qop") {
            None => None,
            Some(list)
                if list
                    .split(',')
                    .any(|s| s.trim().eq_ignore_ascii_case("auth")) =>
            {
                Some("auth")
            }
            Some(list)
                if list
                    .split(',')
                    .any(|s| s.trim().eq_ignore_ascii_case("auth-int")) =>
            {
                Some("auth-int")
            }
            _ => return None,
        };
        Some(Self {
            fields,
            algorithm,
            session,
            qop,
        })
    }

    fn header(
        &self,
        user: &str,
        password: &str,
        authority: &str,
        cnonce: &str,
        count: u32,
    ) -> Option<header::HeaderValue> {
        let realm = self.fields.get("realm")?;
        let nonce = self.fields.get("nonce")?;
        let hash = |v: &str| self.algorithm.hash(v);
        let mut ha1 = hash(&format!("{user}:{realm}:{password}"));
        if self.session {
            ha1 = hash(&format!("{ha1}:{nonce}:{cnonce}"));
        }
        let ha2 = if self.qop == Some("auth-int") {
            hash(&format!("CONNECT:{authority}:{}", hash("")))
        } else {
            hash(&format!("CONNECT:{authority}"))
        };
        let response = if let Some(qop) = self.qop {
            hash(&format!("{ha1}:{nonce}:{count:08x}:{cnonce}:{qop}:{ha2}"))
        } else {
            hash(&format!("{ha1}:{nonce}:{ha2}"))
        };
        let mut parts = Vec::new();
        if self
            .fields
            .get("userhash")
            .is_some_and(|s| s.eq_ignore_ascii_case("true"))
        {
            parts.push(format!(
                "username={}",
                quoted(&hash(&format!("{user}:{realm}")))
            ));
            parts.push("userhash=true".into());
        } else if user.is_ascii() {
            parts.push(format!("username={}", quoted(user)));
        } else {
            // RFC 7616 permits username* on the wire for non-ASCII user names.
            parts.push(format!(
                "username*=UTF-8''{}",
                percent_encoding::utf8_percent_encode(user, percent_encoding::NON_ALPHANUMERIC)
            ));
        }
        let suffix = if self.session { "-sess" } else { "" };
        parts.extend([
            format!("realm={}", quoted(realm)),
            format!("nonce={}", quoted(nonce)),
            format!("uri={}", quoted(authority)),
            format!("response={}", quoted(&response)),
            format!("algorithm={}{suffix}", self.algorithm.name()),
        ]);
        if let Some(qop) = self.qop {
            parts.push(format!("qop={qop}"));
            parts.push(format!("nc={count:08x}"));
        }
        if self.qop.is_some() || self.session {
            parts.push(format!("cnonce={}", quoted(cnonce)));
        }
        if let Some(opaque) = self.fields.get("opaque") {
            parts.push(format!("opaque={}", quoted(opaque)));
        }
        let mut value =
            header::HeaderValue::from_str(&format!("Digest {}", parts.join(", "))).ok()?;
        value.set_sensitive(true);
        Some(value)
    }
}

fn challenges(value: &str) -> Vec<Challenge> {
    let (mut quoting, mut escaped) = (false, false);
    let chunks = value.split(|c| {
        if escaped {
            escaped = false;
        } else if quoting && c == '\\' {
            escaped = true;
        } else if c == '"' {
            quoting = !quoting;
        } else if !quoting && c == ',' {
            return true;
        }
        false
    });
    let mut selected: Option<Fields> = None;
    let mut out = Vec::new();
    for part in chunks {
        let part = part.trim();
        let end = part.bytes().take_while(|c| token(*c)).count();
        let (word, next) = part.split_at(end);
        let rest = next.trim_start();
        if rest.starts_with('=') {
            if let Some(fields) = &mut selected
                && insert(fields, part).is_none()
            {
                selected = None;
            }
        } else {
            if let Some(c) = selected.take().and_then(Challenge::parse) {
                out.push(c);
            }
            if word.eq_ignore_ascii_case("Digest") && next.len() > rest.len() {
                let mut fields = Fields::new();
                if insert(&mut fields, rest).is_some() {
                    selected = Some(fields);
                }
            }
        }
    }
    if !quoting
        && !escaped
        && let Some(c) = selected.and_then(Challenge::parse)
    {
        out.push(c);
    }
    out
}

pub(super) fn authorization(
    headers: &header::HeaderMap,
    proxy: &Url,
    api: &Url,
    state: &DigestState,
) -> Result<Option<header::HeaderValue>, Error> {
    let selected = headers
        .get_all(header::PROXY_AUTHENTICATE)
        .iter()
        .filter_map(|value| value.to_str().ok())
        .flat_map(challenges)
        .max_by_key(|c| (c.algorithm, c.session));
    let Some(selected) = selected else {
        return Ok(None);
    };
    let user = percent_decode_str(proxy.username())
        .decode_utf8()
        .map_err(|_| Error::Origin)?;
    let password = percent_decode_str(proxy.password().unwrap_or(""))
        .decode_utf8()
        .map_err(|_| Error::Origin)?;
    let authority = format!(
        "{}:{}",
        api.host_str().ok_or(Error::Origin)?,
        api.port_or_known_default().ok_or(Error::Origin)?
    );
    let (cnonce, count) = state.next(selected.fields.get("nonce").ok_or(Error::Protocol)?)?;
    selected
        .header(&user, &password, &authority, &cnonce, count)
        .map(Some)
        .ok_or(Error::Protocol)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn digest_binds_the_connect_authority_and_uses_known_response_hashes() {
        for (algorithm, expected) in [
            ("MD5", "76e28345485621fdae6efb630e0c70d9"),
            (
                "SHA-256",
                "bd35717705180f575ae9eb5a6708c1aee71664c018a6b64bc84478bc529b8d9c",
            ),
        ] {
            let text = format!(
                "Digest realm=\"synthetic proxy\", nonce=fixture-nonce, qop=\"auth,auth-int\", algorithm={algorithm}"
            );
            let c = challenges(&text).pop().unwrap();
            let value = c
                .header(
                    "fixture",
                    "kit-password",
                    "127.0.0.1:28431",
                    "fixture-cnonce",
                    1,
                )
                .unwrap();
            let text = value.to_str().unwrap();
            assert!(value.is_sensitive());
            assert!(text.contains(&format!("response=\"{expected}\"")));
            assert!(text.contains("uri=\"127.0.0.1:28431\""));
        }
    }

    #[test]
    fn parallel_requests_use_distinct_counts_and_a_rotated_nonce_starts_at_one() {
        let state = DigestState::default();
        let results = std::thread::scope(|scope| {
            let readers: Vec<_> = (0..8)
                .map(|_| scope.spawn(|| state.next("first").unwrap()))
                .collect();
            readers
                .into_iter()
                .map(|r| r.join().unwrap())
                .collect::<Vec<_>>()
        });
        let mut counts = results.iter().map(|(_, count)| *count).collect::<Vec<_>>();
        counts.sort_unstable();
        assert_eq!(counts, (1..=8).collect::<Vec<_>>());
        assert!(results.iter().all(|(client, _)| client == &results[0].0));
        let rotated = state.next("second").unwrap();
        assert_eq!(rotated.1, 1);
        assert_ne!(rotated.0, results[0].0);
        assert_eq!(state.next("first").unwrap(), (results[0].0.clone(), 9));
    }

    #[test]
    fn quoted_commas_and_unusable_or_ambiguous_challenges_do_not_select_credentials() {
        for text in [
            "Basic realm=\"other, Digest realm=x, nonce=y\"",
            "Digest realm=a, nonce=b, nonce=c",
            "Digest realm=a, nonce=b, qop=other",
            "Digest realm=a, nonce=b, algorithm=unknown",
            "Digest realm=\"unfinished, nonce=b",
        ] {
            assert!(challenges(text).is_empty(), "{text}");
        }
        let text =
            "Negotiate, Digest realm=\"a,b\", nonce=\"x\\\"y\", opaque=\"a,b\", Basic realm=x";
        let c = challenges(text).pop().unwrap();
        assert_eq!(c.fields["realm"], "a,b");
        assert_eq!(c.fields["nonce"], "x\"y");
    }
}
