use std::{
    net::{Ipv4Addr, Ipv6Addr},
    time::Duration,
};

use futures_util::{SinkExt, StreamExt};
use ifw_immich::realtime::{IncomingMessage, MAX_MESSAGE_BYTES};
use reqwest::{Certificate, Client, Method, RequestBuilder, Response, StatusCode, Url, header};
use tokio_tungstenite::WebSocketStream;
use tokio_tungstenite::tungstenite::{
    self, Message,
    handshake::{client::generate_key, derive_accept_key},
    protocol::{Role, WebSocketConfig},
};

use crate::Error;

pub(crate) const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
pub(crate) type Socket = WebSocketStream<reqwest::Upgraded>;

pub(crate) struct Transport {
    api: Url,
    endpoint: Url,
    client: Client,
    header: header::HeaderValue,
    pub namespace: String,
}

/// Select the proxy for one HTTPS origin with the Unix System.Net precedence.
/// The endpoint is kept separate so the loopback harness can check its
/// ownership even when the destination is on the bypass list.
pub(crate) struct LinuxHttpsProxy {
    pub endpoint: Option<Url>,
    bypass: bool,
}

fn unix_proxy_endpoint(value: &str) -> Option<Url> {
    let (scheme, authority) = value.split_once("://").unwrap_or(("http", value));
    if !["http", "https", "socks4", "socks4a", "socks5"]
        .iter()
        .any(|supported| scheme.eq_ignore_ascii_case(supported))
    {
        return None;
    }
    // System.Net reads the decimal port prefix after the host, ignoring a
    // subsequent suffix. A colon with no valid port falls through to the
    // next environment variable. Ignore colons in credentials and IPv6.
    let host = authority
        .rsplit_once('@')
        .map_or(authority, |(_, host)| host);
    let colon = host
        .rfind(':')
        .filter(|pos| host.find(']').is_none_or(|end| *pos > end));
    if let Some(colon) = colon {
        let port = &host[colon + 1..];
        let digits = port.bytes().take_while(u8::is_ascii_digit).count();
        let port_number = port[..digits].parse::<u16>().ok()?;
        let name = &authority[..authority.len() - port.len() - 1];
        return Url::parse(&format!("{scheme}://{name}:{port_number}")).ok();
    }
    Url::parse(&format!("{scheme}://{authority}")).ok()
}

/// System.Uri compares the literal bypass entry to its canonical Host. Some
/// bracketed IPv6 hosts end in dotted IPv4 there, while Url writes hexadecimal.
fn embedded_ipv4_host(host: &str) -> Option<String> {
    let raw = host.strip_prefix('[')?.strip_suffix(']')?;
    let address = raw.parse::<Ipv6Addr>().ok()?;
    let [a, b, c, d, e, f, high, _] = address.segments();
    let translated =
        [a, b, c, d] == [0; 4] && high != 0 && matches!((e, f), (0, 0 | 0xffff) | (0xffff, 0));
    if !translated && (e, f) != (0, 0x5efe) {
        return None;
    }
    // A trailing compressed pair can occur in an ISATAP address. Otherwise
    // the final two hexadecimal fields are explicit in these address forms.
    let prefix = raw
        .strip_suffix("::")
        .or_else(|| raw.rsplitn(3, ':').nth(2))?;
    let [.., w, x, y, z] = address.octets();
    Some(format!("[{prefix}:{}]", Ipv4Addr::new(w, x, y, z)))
}

impl LinuxHttpsProxy {
    pub fn from_environment(api: &Url, read: impl Fn(&str) -> Option<String>) -> Self {
        let endpoint = ["https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]
            .iter()
            .filter_map(|name| read(name))
            .find_map(|value| unix_proxy_endpoint(&value));
        let excluded = read("no_proxy").or_else(|| read("NO_PROXY"));
        let host = api.host_str().unwrap_or_default();
        let embedded = embedded_ipv4_host(host);
        let host = embedded.as_deref().unwrap_or(host);
        let bypass = excluded.as_deref().is_some_and(|list| {
            list.split(',')
                .map(str::trim)
                .filter(|entry| !entry.is_empty())
                .any(|entry| {
                    let Some(domain) = entry.strip_prefix('.') else {
                        return host.eq_ignore_ascii_case(entry);
                    };
                    host.eq_ignore_ascii_case(domain)
                        || host
                            .get(host.len().saturating_sub(entry.len())..)
                            .is_some_and(|tail| tail.eq_ignore_ascii_case(entry))
                })
        });
        Self { endpoint, bypass }
    }

    pub fn route(self) -> Option<Url> {
        self.endpoint.filter(|_| !self.bypass)
    }
}

fn escaped_byte(path: &str) -> Option<u8> {
    let digits = path.strip_prefix('%')?.get(..2)?;
    if !digits.bytes().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    u8::from_str_radix(digits, 16).ok()
}

/// System.Uri re-escapes valid IRI path characters in uppercase. Escapes for
/// private-use, control, noncharacter or invalid UTF-8 bytes retain their spelling.
fn iri_escape_length(path: &str, first: u8) -> Option<usize> {
    let size = match first {
        0xc2..=0xdf => 2,
        0xe0..=0xef => 3,
        0xf0..=0xf4 => 4,
        _ => return None,
    };
    let mut scalar = [first; 4];
    for (index, byte) in scalar[..size].iter_mut().enumerate().skip(1) {
        *byte = escaped_byte(path.get(index * 3..)?)?;
    }
    let value = std::str::from_utf8(&scalar[..size]).ok()?.chars().next()? as u32;
    let eligible = match value {
        0xa0..=0xd7ff | 0xf900..=0xfdcf | 0xfdf0..=0xffef => true,
        0x10000..=0xdfffd | 0xe1000..=0xefffd => value & 0xffff <= 0xfffd,
        _ => false,
    };
    eligible.then_some(3 * size)
}

/// Translate the ASCII serialization of an HTTP(S) URL path to the spelling
/// used by the shipping System.Uri reader. Preserve escaped path separators.
fn shipping_path(mut path: &str) -> String {
    let mut out = String::with_capacity(path.len());
    while let Some(&first) = path.as_bytes().first() {
        if let Some(byte) = escaped_byte(path) {
            if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~') {
                out.push(char::from(byte));
            } else if let Some(len) = iri_escape_length(path, byte) {
                out.push_str(&path[..len].to_ascii_uppercase());
                path = &path[len..];
                continue;
            } else {
                out.push_str(&path[..3]);
            }
            path = &path[3..];
        } else {
            match first {
                b'%' => out.push_str("%25"),
                b'|' => out.push_str("%7C"),
                b'^' => out.push_str("%5E"),
                _ => out.push(char::from(first)),
            }
            path = &path[1..];
        }
    }
    out
}

impl Transport {
    pub fn new(
        mut api: Url,
        allow_http: bool,
        api_key: &str,
        roots: Option<Vec<Certificate>>,
        https_proxy: Option<Url>,
    ) -> Result<Self, Error> {
        if !(api.scheme() == "https" || allow_http && api.scheme() == "http")
            || api.host().is_none()
            || !api.username().is_empty()
            || api.password().is_some()
        {
            return Err(Error::Origin);
        }
        // SocketIOClient uses the URL path (minus terminal "api") as its
        // namespace; Engine.IO always uses the distinct default transport path.
        api.set_path(&shipping_path(api.path()));
        let segments: Vec<_> = api
            .path_segments()
            .ok_or(Error::Origin)?
            .filter(|s| !s.is_empty())
            .collect();
        let prefix = if segments
            .last()
            .is_some_and(|s| s.eq_ignore_ascii_case("api"))
        {
            &segments[..segments.len() - 1]
        } else {
            &segments[..]
        };
        let namespace = format!("/{}", prefix.join("/"));
        let endpoint = api.join("/socket.io/").map_err(|_| Error::Origin)?;
        let mut header = header::HeaderValue::from_str(api_key).map_err(|_| Error::Origin)?;
        header.set_sensitive(true);
        let mut builder = Client::builder()
            .tls_backend_rustls()
            .http1_only()
            .no_proxy()
            .https_only(!allow_http)
            .redirect(reqwest::redirect::Policy::none())
            .retry(reqwest::retry::never())
            .connect_timeout(CONNECT_TIMEOUT)
            .timeout(Duration::from_secs(120));
        if let Some(roots) = roots {
            builder = builder.tls_certs_only(roots);
        }
        if let Some(proxy) = https_proxy {
            builder = builder.proxy(reqwest::Proxy::https(proxy)?);
        }
        Ok(Self {
            api,
            endpoint,
            namespace,
            header,
            client: builder.build().map_err(|_| Error::Transport)?,
        })
    }

    fn uri(&self, transport: &str, sid: Option<&str>) -> Url {
        let mut url = self.endpoint.clone();
        {
            let mut query = url.query_pairs_mut();
            query
                .append_pair("EIO", "4")
                .append_pair("transport", transport);
            if let Some(sid) = sid {
                query.append_pair("sid", sid);
            }
        }
        url
    }

    fn request(&self, method: Method, url: Url) -> Result<RequestBuilder, Error> {
        if url.origin() != self.api.origin()
            || !url.username().is_empty()
            || url.password().is_some()
        {
            return Err(Error::Origin);
        }
        Ok(self
            .client
            .request(method, url)
            .header("x-api-key", &self.header))
    }

    pub async fn poll(&self, sid: Option<&str>) -> Result<Vec<u8>, Error> {
        let resp = self
            .request(Method::GET, self.uri("polling", sid))?
            .send()
            .await?;
        bounded_ok_body(resp).await
    }

    pub async fn post(&self, sid: &str, packet: String, max_payload: usize) -> Result<(), Error> {
        if packet.len() > max_payload.min(MAX_MESSAGE_BYTES) {
            return Err(Error::Limit);
        }
        let resp = self
            .request(Method::POST, self.uri("polling", Some(sid)))?
            .header(header::CONTENT_TYPE, "text/plain;charset=UTF-8")
            .body(packet)
            .send()
            .await?;
        if bounded_ok_body(resp).await? != b"ok" {
            return Err(Error::Protocol);
        }
        Ok(())
    }

    pub async fn websocket(&self, sid: Option<&str>) -> Result<Socket, Error> {
        // Keep the exact origin, headers, TLS verifier and no-redirect policy of
        // polling. Only switch the I/O stream after the RFC 6455 response.
        let key = generate_key();
        let accept = derive_accept_key(key.as_bytes());
        let resp = self
            .request(Method::GET, self.uri("websocket", sid))?
            .header(header::CONNECTION, "Upgrade")
            .header(header::UPGRADE, "websocket")
            .header(header::SEC_WEBSOCKET_VERSION, "13")
            .header(header::SEC_WEBSOCKET_KEY, key)
            .send()
            .await?;
        let headers = resp.headers();
        if resp.status() != StatusCode::SWITCHING_PROTOCOLS {
            return Err(Error::Status(resp.status().as_u16()));
        }
        let contains_upgrade = headers
            .get_all(header::CONNECTION)
            .iter()
            .filter_map(|v| v.to_str().ok())
            .flat_map(|s| s.split(','))
            .any(|s| s.trim().eq_ignore_ascii_case("upgrade"));
        let mut upgrades = headers.get_all(header::UPGRADE).iter();
        let mut challenges = headers.get_all(header::SEC_WEBSOCKET_ACCEPT).iter();
        if !contains_upgrade
            || !upgrades
                .next()
                .is_some_and(|h| h.as_bytes().eq_ignore_ascii_case(b"websocket"))
            || upgrades.next().is_some()
            || !challenges
                .next()
                .is_some_and(|h| h.as_bytes() == accept.as_bytes())
            || challenges.next().is_some()
            || headers.contains_key(header::SEC_WEBSOCKET_EXTENSIONS)
            || headers.contains_key(header::SEC_WEBSOCKET_PROTOCOL)
        {
            return Err(Error::Protocol);
        }
        let config = WebSocketConfig::default()
            .read_buffer_size(16 * 1024)
            .write_buffer_size(16 * 1024)
            .max_frame_size(Some(MAX_MESSAGE_BYTES))
            .max_message_size(Some(MAX_MESSAGE_BYTES))
            .max_write_buffer_size(MAX_MESSAGE_BYTES + 32 * 1024);
        Ok(Socket::from_raw_socket(resp.upgrade().await?, Role::Client, Some(config)).await)
    }

    pub async fn probe(&self, sid: &str) -> Result<Socket, Error> {
        let mut ws = self.websocket(Some(sid)).await?;
        ws.send(Message::text("2probe")).await?;
        loop {
            match ws.next().await.ok_or(Error::Disconnected)?? {
                Message::Text(text) if text == "3probe" => return Ok(ws),
                Message::Ping(_) => ws.flush().await?,
                Message::Pong(_) => {}
                Message::Close(_) => {
                    ws.flush().await?;
                    return Err(Error::Disconnected);
                }
                _ => return Err(Error::Protocol),
            }
        }
    }

    /// The feasibility consumer demonstrates a real bounded HTTP inventory
    /// request after a refresh. Its fixture supplies only an empty album list.
    pub async fn fixture_inventory(&self) -> Result<(), Error> {
        let mut url = self.api.clone();
        url.set_query(None);
        url.set_fragment(None);
        url.path_segments_mut()
            .map_err(|_| Error::Origin)?
            .pop_if_empty()
            .push("albums");
        let resp = self.request(Method::GET, url)?.send().await?;
        if bounded_ok_body(resp).await? == b"[]" {
            Ok(())
        } else {
            Err(Error::Protocol)
        }
    }
}

async fn bounded_ok_body(mut response: Response) -> Result<Vec<u8>, Error> {
    if response.status() != StatusCode::OK {
        return Err(Error::Status(response.status().as_u16()));
    }
    if response
        .content_length()
        .is_some_and(|n| n > MAX_MESSAGE_BYTES as u64)
    {
        return Err(Error::Limit);
    }
    let mut input = IncomingMessage::default();
    while let Some(chunk) = response.chunk().await? {
        input.append(&chunk).map_err(|_| Error::Limit)?;
    }
    input.finish().map_err(|_| Error::Limit)
}

impl From<reqwest::Error> for Error {
    fn from(value: reqwest::Error) -> Self {
        if value.is_timeout() {
            Self::Timeout
        } else {
            Self::Transport
        }
    }
}

impl From<tungstenite::Error> for Error {
    fn from(value: tungstenite::Error) -> Self {
        match value {
            tungstenite::Error::Capacity(_) => Self::Limit,
            tungstenite::Error::ConnectionClosed
            | tungstenite::Error::AlreadyClosed
            | tungstenite::Error::Protocol(
                tungstenite::error::ProtocolError::ResetWithoutClosingHandshake,
            ) => Self::Disconnected,
            _ => Self::Transport,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn proxy_for(host: &str, environment: &[(&str, &str)]) -> Option<Url> {
        let api = Url::parse(&format!("https://{host}/api")).unwrap();
        LinuxHttpsProxy::from_environment(&api, |name| {
            environment
                .iter()
                .find(|(key, _)| *key == name)
                .map(|(_, value)| value.to_string())
        })
        .route()
    }

    #[test]
    fn linux_https_uses_the_first_valid_protocol_then_all_proxy() {
        let lower = "127.0.0.1:8200";
        let upper = "http://[::1]:8201";
        let all = "http://127.0.0.1:8202";
        let expected = Url::parse("http://127.0.0.1:8200").unwrap();
        for value in [
            lower,
            "http://127.0.0.1:8200x",
            "http://127.0.0.1:8200/path",
        ] {
            assert_eq!(
                proxy_for(
                    "example.test",
                    &[
                        ("https_proxy", value),
                        ("HTTPS_PROXY", upper),
                        ("all_proxy", all)
                    ]
                ),
                Some(expected.clone())
            );
        }
        for invalid in ["", "http://[", "http://127.0.0.1:", "ftp://127.0.0.1:8200"] {
            assert_eq!(
                proxy_for(
                    "example.test",
                    &[
                        ("https_proxy", invalid),
                        ("HTTPS_PROXY", upper),
                        ("all_proxy", all)
                    ]
                ),
                Some(Url::parse(upper).unwrap())
            );
        }
        assert_eq!(
            proxy_for(
                "example.test",
                &[
                    ("HTTP_PROXY", upper),
                    ("all_proxy", lower),
                    ("ALL_PROXY", all)
                ]
            ),
            Some(expected)
        );
        assert_eq!(proxy_for("example.test", &[("HTTP_PROXY", upper)]), None);
    }

    #[test]
    fn linux_https_bypass_matches_hosts_and_dot_domains_with_lowercase_precedence() {
        for (host, exclusions, bypass) in [
            ("example.test", " , EXAMPLE.TEST , ", true),
            ("a.example.test", "example.test", false),
            ("a.example.test", ".example.test", true),
            ("example.test", ".example.test", true),
            ("otherexample.test", ".example.test", false),
            ("127.0.0.1", "*", false),
            ("127.0.0.1", "127.0.0.1:443", false),
            ("[::1]", "[::1]", true),
            ("[::1]", "::1", false),
            ("[::ffff:7f00:1]", "[::ffff:127.0.0.1]", true),
            ("[::ffff:127.0.0.1]", "[::ffff:7f00:1]", false),
            ("[::7f00:1]", "[::127.0.0.1]", true),
            ("[::ffff:0:7f00:1]", "[::ffff:0:127.0.0.1]", true),
            ("[::ffff:1]", "[::ffff:0.0.0.1]", false),
            ("[64:ff9b::7f00:1]", "[64:ff9b::127.0.0.1]", false),
            (
                "[2001:db8::5efe:7f00:1]",
                "[2001:db8::5efe:127.0.0.1]",
                true,
            ),
            (
                "[2001:db8:1:2:0:5efe::]",
                "[2001:db8:1:2:0:5efe:0.0.0.0]",
                true,
            ),
            ("127.0.0.1", "", false),
        ] {
            assert_eq!(
                proxy_for(
                    host,
                    &[
                        ("HTTPS_PROXY", "127.0.0.1:8200"),
                        ("no_proxy", exclusions),
                        ("NO_PROXY", host)
                    ]
                )
                .is_none(),
                bypass,
                "{host} {exclusions}"
            );
        }
    }

    #[test]
    fn authenticated_requests_require_the_configured_scheme_host_port_and_no_user_info() {
        let _ = rustls::crypto::ring::default_provider().install_default();
        let api = Url::parse("https://127.0.0.1:4443/collection/api").unwrap();
        let transport = Transport::new(api, false, "synthetic", Some(Vec::new()), None).unwrap();
        assert_eq!(transport.namespace, "/collection");
        for foreign in [
            "http://127.0.0.1:4443/socket.io/",
            "https://127.0.0.1:4444/socket.io/",
            "https://127.0.0.2:4443/socket.io/",
            "https://other@127.0.0.1:4443/socket.io/",
        ] {
            assert!(matches!(
                transport.request(Method::GET, Url::parse(foreign).unwrap()),
                Err(Error::Origin)
            ));
        }
        let safe = transport.uri("polling", Some("session&transport=other"));
        assert_eq!(safe.path(), "/socket.io/");
        assert_eq!(
            safe.query_pairs().last().unwrap().1,
            "session&transport=other"
        );
        assert!(transport.request(Method::GET, safe).is_ok());
    }

    #[test]
    fn shipping_paths_decode_unreserved_characters_once_and_keep_escaped_separators() {
        for (path, expected) in [
            ("/%63ollection/caf%c3%a9/%61PI", "/collection/caf%C3%A9/aPI"),
            ("/t%2Fr%3fp%23s/%252f", "/t%2Fr%3fp%23s/%252f"),
            ("/%7e%2d%2e%5f/%20", "/~-._/%20"),
            ("/%f0%9f%8e%9e", "/%F0%9F%8E%9E"),
            ("/%c2%80/%ee%80%80/%ff", "/%c2%80/%ee%80%80/%ff"),
            ("/%f0%9f%bf%bf/%c3%2f", "/%f0%9f%bf%bf/%c3%2f"),
            ("/discount%/rate|fee", "/discount%25/rate%7Cfee"),
        ] {
            assert_eq!(shipping_path(path), expected);
        }
    }
}
