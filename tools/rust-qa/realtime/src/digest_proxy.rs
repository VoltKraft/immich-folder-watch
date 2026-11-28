//! Digest authentication for a challenged request to the selected Linux HTTP proxy.
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
    fn hash(self, value: &[u8]) -> String {
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

/// The method, request-target and entity bytes in the proxy's HTTP exchange.
pub(super) struct DigestRequest<'a> {
    pub method: &'a reqwest::Method,
    pub target: &'a str,
    pub entity: &'a [u8],
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

fn insert(fields: &mut Fields, key_value: &[u8]) -> Option<()> {
    let (key, value) = std::str::from_utf8(key_value).ok()?.split_once('=')?;
    let key = key.trim_ascii();
    if key.is_empty() || !key.bytes().all(token) {
        return None;
    }
    fields
        .insert(key.to_ascii_lowercase(), unquote(value.trim_ascii())?)
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
        request: &DigestRequest<'_>,
        cnonce: &str,
        count: u32,
    ) -> Option<header::HeaderValue> {
        let realm = self.fields.get("realm")?;
        let nonce = self.fields.get("nonce")?;
        let hash = |v: &str| self.algorithm.hash(v.as_bytes());
        let mut ha1 = hash(&format!("{user}:{realm}:{password}"));
        if self.session {
            ha1 = hash(&format!("{ha1}:{nonce}:{cnonce}"));
        }
        let mut a2 = format!("{}:{}", request.method, request.target);
        if self.qop == Some("auth-int") {
            a2.push(':');
            a2.push_str(&self.algorithm.hash(request.entity));
        }
        let ha2 = hash(&a2);
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
            format!("uri={}", quoted(request.target)),
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
        let response = format!("Digest {}", parts.join(", "));
        let mut value = header::HeaderValue::from_bytes(response.as_bytes()).ok()?;
        value.set_sensitive(true);
        Some(value)
    }
}

fn challenges(value: &[u8]) -> Vec<Challenge> {
    // Scheme and parameter boundaries use ASCII. Decode only the selected
    // Digest parameters so another scheme's opaque bytes cannot hide one.
    let (mut quoting, mut escaped) = (false, false);
    let chunks = value.split(|&c| {
        if escaped {
            escaped = false;
        } else if quoting && c == b'\\' {
            escaped = true;
        } else if c == b'"' {
            quoting = !quoting;
        } else if !quoting && c == b',' {
            return true;
        }
        false
    });
    let mut selected: Option<Fields> = None;
    let mut out = Vec::new();
    for part in chunks {
        let part = part.trim_ascii();
        let end = part.iter().take_while(|&&c| token(c)).count();
        let (word, next) = part.split_at(end);
        let rest = next.trim_ascii_start();
        if rest.starts_with(b"=") {
            if let Some(fields) = &mut selected
                && insert(fields, part).is_none()
            {
                selected = None;
            }
        } else {
            if let Some(c) = selected.take().and_then(Challenge::parse) {
                out.push(c);
            }
            if word.eq_ignore_ascii_case(b"Digest") && next.len() > rest.len() {
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
    request: &DigestRequest<'_>,
    state: &DigestState,
) -> Result<Option<header::HeaderValue>, Error> {
    let selected = headers
        .get_all(header::PROXY_AUTHENTICATE)
        .iter()
        .flat_map(|value| challenges(value.as_bytes()))
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
    let (cnonce, count) = state.next(selected.fields.get("nonce").ok_or(Error::Protocol)?)?;
    selected
        .header(&user, &password, request, &cnonce, count)
        .map(Some)
        .ok_or(Error::Protocol)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn answer(raw: &[u8]) -> Option<header::HeaderValue> {
        let mut headers = header::HeaderMap::new();
        headers.insert(
            header::PROXY_AUTHENTICATE,
            header::HeaderValue::from_bytes(raw).unwrap(),
        );
        let proxy = Url::parse("http://fixture:kit-password@proxy.example/").unwrap();
        let request = DigestRequest {
            method: &reqwest::Method::CONNECT,
            target: "example.test:80",
            entity: &[],
        };
        authorization(&headers, &proxy, &request, &DigestState::default()).unwrap()
    }

    #[test]
    fn utf8_realm_is_hashed_and_echoed_with_its_original_bytes() {
        let challenge =
            b"Digest realm=\"M\xc3\xbcnchen\", charset=UTF-8, nonce=n, algorithm=SHA-256";
        let response = answer(challenge).unwrap();
        assert!(response.is_sensitive());
        assert_eq!(response.as_bytes(), b"Digest username=\"fixture\", realm=\"M\xc3\xbcnchen\", nonce=\"n\", uri=\"example.test:80\", response=\"c48d66d8e12f56b9344be86fbb3a8b05fe9a849499c22e614bb522ebdc939616\", algorithm=SHA-256");
    }

    #[test]
    fn other_challenges_do_not_hide_a_valid_digest_and_invalid_digest_bytes_are_rejected() {
        let ascii: &[u8] = b"Digest realm=ASCII, nonce=n, algorithm=SHA-256";
        let expected = answer(ascii).unwrap();
        for other in [
            &b"Basic realm=\"M\xc3\xbcnchen, mixed\""[..],
            &b"Basic realm=\"opaque \xff, Digest realm=x\""[..],
            &b"Digest realm=\"bad\xff\", nonce=n, algorithm=SHA-256"[..],
            &b"Digest realm=first, nonce=\"bad\xff\", algorithm=SHA-256"[..],
        ] {
            assert!(answer(other).is_none());
            assert_eq!(
                answer(&[other, b", ", ascii].concat()).unwrap().as_bytes(),
                expected.as_bytes()
            );
            assert_eq!(
                answer(&[ascii, b", ", other].concat()).unwrap().as_bytes(),
                expected.as_bytes()
            );
        }
    }

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
            let c = challenges(text.as_bytes()).pop().unwrap();
            let value = c
                .header(
                    "fixture",
                    "kit-password",
                    &DigestRequest {
                        method: &reqwest::Method::CONNECT,
                        target: "127.0.0.1:28431",
                        entity: &[],
                    },
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
    fn forward_digest_binds_absolute_targets_and_the_original_entity_bytes() {
        let post = "http://[::1]:8080/socket.io/?sid=a%26b";
        for (method, target, body, algorithm, qop, expected) in [
            (
                reqwest::Method::GET,
                "http://[::1]:8080/a%2Fb?q=x%20y",
                &[][..],
                "MD5",
                "auth",
                "3dbf3a68e683e9cf7a81b067042e4eef",
            ),
            (
                reqwest::Method::POST,
                post,
                &b"\x0040/collection,\xff"[..],
                "SHA-256",
                "auth-int",
                "710528f880dad3bc8fe9763b1b6dc3222c3af0853d76adc0fdfc873818132b34",
            ),
            (
                reqwest::Method::POST,
                post,
                &[][..],
                "SHA-256",
                "auth-int",
                "2359f2c934f82c95ffbcf326f1b0023aa8947a45326c8a3fd4831d400354fcb6",
            ),
        ] {
            let challenge = format!("Digest realm=r, nonce=n, algorithm={algorithm}, qop={qop}");
            let parsed = challenges(challenge.as_bytes()).pop().unwrap();
            let request = DigestRequest {
                method: &method,
                target,
                entity: body,
            };
            let value = parsed
                .header("fixture", "kit-password", &request, "seat", 1)
                .unwrap();
            assert!(value.is_sensitive());
            let text = value.to_str().unwrap();
            assert!(text.contains(&format!("response=\"{expected}\"")));
            assert!(text.contains(&format!("uri=\"{target}\"")));
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
            assert!(challenges(text.as_bytes()).is_empty(), "{text}");
        }
        let text =
            "Negotiate, Digest realm=\"a,b\", nonce=\"x\\\"y\", opaque=\"a,b\", Basic realm=x";
        let c = challenges(text.as_bytes()).pop().unwrap();
        assert_eq!(c.fields["realm"], "a,b");
        assert_eq!(c.fields["nonce"], "x\"y");
    }
}
