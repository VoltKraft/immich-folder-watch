//! A plaintext WebSocket uses CONNECT to the configured
//! proxy, followed by the normal authenticated HTTP upgrade inside the tunnel.

use hyper::{HeaderMap, Request, StatusCode, Uri, client::conn::http1};
use hyper_util::rt::TokioIo;
use reqwest::{Body, Upgraded, Url, header, header::HeaderValue};
use tokio::{
    io::{AsyncRead, AsyncWrite},
    net::TcpStream,
};

use crate::{Error, transport::validate_upgrade};

/// Credentials belong to the selected plaintext relay. Each request first
/// reaches it without proxy authorization, including WebSocket CONNECT.
pub(crate) struct Credentials {
    pub basic: HeaderValue,
    #[cfg(target_os = "linux")]
    pub url: Url,
    #[cfg(target_os = "linux")]
    pub digest: crate::digest_proxy::DigestState,
}

impl Credentials {
    pub fn challenged(
        &self,
        headers: &HeaderMap,
        _method: &reqwest::Method,
        _target: &str,
        _entity: &[u8],
    ) -> Result<Option<HeaderValue>, Error> {
        #[cfg(target_os = "linux")]
        {
            use crate::digest_proxy::{DigestRequest, authorization};
            let request = DigestRequest {
                method: _method,
                target: _target,
                entity: _entity,
            };
            if let Some(value) = authorization(headers, &self.url, &request, &self.digest)? {
                return Ok(Some(value));
            }
        }
        Ok(offers_basic(headers).then(|| self.basic.clone()))
    }
}

fn relay_address(proxy: &Url) -> Result<(&str, u16), Error> {
    // URL serialization brackets IPv6 literals; Tokio expects the host by
    // itself when resolving a (host, port) pair.
    let host = proxy
        .host_str()
        .ok_or(Error::Origin)?
        .trim_matches(['[', ']']);
    let port = proxy
        .port_or_known_default()
        .filter(|p| *p != 0)
        .ok_or(Error::Origin)?;
    if proxy.scheme() != "http"
        || !proxy.username().is_empty()
        || proxy.password().is_some()
        || proxy.path() != "/"
        || proxy.query().is_some()
        || proxy.fragment().is_some()
    {
        return Err(Error::Origin);
    }
    Ok((host, port))
}

pub(crate) fn connect_authority(url: &Url) -> Result<Uri, Error> {
    let host = url.host_str().ok_or(Error::Origin)?;
    // CONNECT uses authority-form, including the port even for the default 80.
    let destination = format!(
        "{host}:{}",
        url.port_or_known_default().ok_or(Error::Origin)?
    );
    Uri::builder()
        .authority(destination.as_str())
        .build()
        .map_err(|_| Error::Origin)
}

fn requests(request: reqwest::Request) -> Result<(Uri, Request<Body>), Error> {
    let url = request.url();
    if url.scheme() != "http" || !url.username().is_empty() || url.password().is_some() {
        return Err(Error::Origin);
    }
    let authority = connect_authority(url)?;
    let mut inner: Request<Body> = request.try_into()?;
    inner.headers_mut().remove(header::PROXY_AUTHORIZATION);
    let host = inner
        .uri()
        .authority()
        .ok_or(Error::Origin)?
        .as_str()
        .parse()
        .map_err(|_| Error::Origin)?;
    let path = inner.uri().path_and_query().ok_or(Error::Origin)?.clone();
    inner.headers_mut().insert(header::HOST, host);
    *inner.uri_mut() = Uri::builder()
        .path_and_query(path)
        .build()
        .map_err(|_| Error::Origin)?;
    Ok((authority, inner))
}

/// Poll the HTTP driver together with its single request. Cancellation drops
/// both futures and the socket; Hyper retains bytes read past the response.
async fn upgrade(
    stream: impl AsyncRead + AsyncWrite + Unpin + Send + 'static,
    request: Request<Body>,
    validate: impl FnOnce(StatusCode, &HeaderMap) -> Result<(), Error>,
) -> Result<Upgraded, Error> {
    let (mut sender, connection) = http1::Builder::new()
        .max_buf_size(64 * 1024)
        .handshake(TokioIo::new(stream))
        .await
        .map_err(|_| Error::Transport)?;
    let exchange = async {
        let response = sender
            .send_request(request)
            .await
            .map_err(|_| Error::Transport)?;
        validate(response.status(), response.headers())?;
        hyper::upgrade::on(response)
            .await
            .map(Upgraded::from)
            .map_err(|_| Error::Transport)
    };
    let drive = async {
        connection
            .with_upgrades()
            .await
            .map_err(|_| Error::Transport)
    };
    let (upgraded, ()) = tokio::try_join!(exchange, drive)?;
    Ok(upgraded)
}

/// Challenge lists may contain quoted commas. An unknown scheme's realm
/// never authorizes releasing credentials to the proxy.
pub(crate) fn offers_basic(headers: &HeaderMap) -> bool {
    headers
        .get_all(header::PROXY_AUTHENTICATE)
        .iter()
        .any(|value| {
            let Ok(value) = value.to_str() else {
                return false;
            };
            let (mut quoted, mut escaped) = (false, false);
            value
                .split(|c| {
                    if escaped {
                        escaped = false;
                    } else if c == '\\' && quoted {
                        escaped = true;
                    } else if c == '"' {
                        quoted = !quoted;
                    } else if c == ',' && !quoted {
                        return true;
                    }
                    false
                })
                .any(|part| {
                    let mut fields = part.split_ascii_whitespace();
                    fields
                        .next()
                        .is_some_and(|scheme| scheme.eq_ignore_ascii_case("basic"))
                        && !fields.next().is_some_and(|params| params.starts_with('='))
                })
        })
}

fn connect_request(
    authority: &Uri,
    authorization: Option<&HeaderValue>,
) -> Result<Request<Body>, Error> {
    let mut request = Request::connect(authority.clone()).header(
        header::HOST,
        authority.authority().ok_or(Error::Origin)?.as_str(),
    );
    if let Some(authorization) = authorization {
        request = request.header(header::PROXY_AUTHORIZATION, authorization);
    }
    request.body(Body::default()).map_err(|_| Error::Origin)
}

async fn open_tunnel(
    address: (&str, u16),
    authority: &Uri,
    authorization: Option<&HeaderValue>,
    challenge: impl FnOnce(&HeaderMap) -> Result<(), Error>,
) -> Result<Upgraded, Error> {
    let request = connect_request(authority, authorization)?;
    let stream = TcpStream::connect(address)
        .await
        .map_err(|_| Error::Transport)?;
    upgrade(stream, request, |status, headers| {
        if status.is_success() {
            Ok(())
        } else {
            if status == StatusCode::PROXY_AUTHENTICATION_REQUIRED {
                challenge(headers)?;
            }
            Err(Error::Status(status.as_u16()))
        }
    })
    .await
}

pub(crate) async fn websocket(
    relay: &Url,
    credentials: Option<&Credentials>,
    request: reqwest::Request,
    accept: &str,
) -> Result<Upgraded, Error> {
    let (authority, inner) = requests(request)?;
    let address = relay_address(relay)?;
    let mut retry = None;
    let first = open_tunnel(address, &authority, None, |headers| {
        if let Some(credentials) = credentials {
            let target = authority.authority().ok_or(Error::Origin)?.as_str();
            retry = credentials.challenged(headers, &reqwest::Method::CONNECT, target, &[])?;
        }
        Ok(())
    })
    .await;
    let tunnel = match (first, retry) {
        (Err(Error::Status(407)), Some(value)) => {
            open_tunnel(address, &authority, Some(&value), |_| Ok(())).await?
        }
        (result, _) => result?,
    };
    upgrade(tunnel, inner, |status, headers| {
        validate_upgrade(status, headers, accept)
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(target_os = "linux")]
    #[test]
    fn forward_requests_and_connect_share_nonce_counts_and_prefer_an_offered_digest() {
        let credentials = Credentials {
            url: Url::parse("http://fixture:kit-password@proxy.example/").unwrap(),
            basic: HeaderValue::from_static("Basic synthetic"),
            digest: Default::default(),
        };
        let mut headers = HeaderMap::new();
        headers.append(
            header::PROXY_AUTHENTICATE,
            HeaderValue::from_static("Digest realm=r, nonce=n, algorithm=unknown"),
        );
        assert!(
            credentials
                .challenged(&headers, &reqwest::Method::GET, "http://example.test/", &[])
                .unwrap()
                .is_none()
        );
        headers.clear();
        headers.append(
            header::PROXY_AUTHENTICATE,
            HeaderValue::from_static("Basic realm=r"),
        );
        headers.append(
            header::PROXY_AUTHENTICATE,
            HeaderValue::from_static("Digest realm=r, nonce=n, qop=auth"),
        );
        for (count, (method, target)) in [
            (reqwest::Method::GET, "http://example.test/api/albums"),
            (
                reqwest::Method::POST,
                "http://example.test/socket.io/?sid=s",
            ),
            (reqwest::Method::CONNECT, "example.test:80"),
        ]
        .iter()
        .enumerate()
        {
            let value = credentials
                .challenged(&headers, method, target, &[])
                .unwrap()
                .unwrap();
            let text = value.to_str().unwrap();
            assert!(text.starts_with("Digest "));
            assert!(text.contains(&format!("nc={:08x}", count + 1)));
            assert!(text.contains(&format!("uri=\"{target}\"")));
        }
    }

    #[test]
    fn only_an_offered_basic_scheme_triggers_the_retry() {
        for (challenges, expected) in [
            (r#"Digest realm="protected, Basic realm", nonce="a""#, false),
            (r#"Digest realm="quoted\", Basic", Basic = data"#, false),
            (
                r#"Digest realm="protected, Basic", bAsIc realm="proxy""#,
                true,
            ),
            ("Basic", true),
            ("Bearer", false),
        ] {
            let mut headers = HeaderMap::new();
            headers.append(
                header::PROXY_AUTHENTICATE,
                HeaderValue::from_str(challenges).unwrap(),
            );
            assert_eq!(offers_basic(&headers), expected);
        }
    }

    #[test]
    fn relay_preserves_dns_and_native_ip_hosts_for_tcp_connect() {
        for (url, host, port) in [
            ("http://proxy.example", "proxy.example", 80),
            ("http://192.0.2.14:8031", "192.0.2.14", 8031),
            ("http://[2001:db8::1]:8888", "2001:db8::1", 8888),
        ] {
            let relay = Url::parse(url).unwrap();
            assert_eq!(relay_address(&relay), Ok((host, port)));
        }
    }

    #[tokio::test]
    async fn websocket_connects_through_the_configured_localhost_proxy() {
        use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
        use tokio::net::TcpListener;

        let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let proxy = Url::parse(&format!("http://localhost:{port}/")).unwrap();
        assert!(
            tokio::net::lookup_host(("localhost", port))
                .await
                .unwrap()
                .all(|a| a.ip().is_loopback())
        );
        let _ = rustls::crypto::ring::default_provider().install_default();
        let transport = crate::transport::Transport::new(
            Url::parse("http://127.0.0.1:1/api").unwrap(),
            true,
            "synthetic",
            Some(Vec::new()),
            Some(proxy),
        )
        .unwrap();
        let observe = async {
            let (stream, _) = listener.accept().await.unwrap();
            let mut reader = BufReader::new(stream);
            let mut first = String::new();
            reader.read_line(&mut first).await.unwrap();
            assert_eq!(first, "CONNECT 127.0.0.1:1 HTTP/1.1\r\n");
            loop {
                let mut line = String::new();
                assert!(reader.read_line(&mut line).await.unwrap() > 0);
                if line == "\r\n" {
                    break;
                }
            }
            reader
                .get_mut()
                .write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                .await
                .unwrap();
        };
        let (result, ()) = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            tokio::join!(transport.websocket(None), observe)
        })
        .await
        .unwrap();
        assert!(matches!(result, Err(Error::Status(403))));
    }

    #[test]
    fn connect_includes_default_and_ipv6_ports_but_only_the_inner_origin_get_has_the_key() {
        for (url, connect_host, inner_host) in [
            (
                "http://127.0.0.1/socket.io/?sid=a%26b",
                "127.0.0.1:80",
                "127.0.0.1",
            ),
            (
                "http://[::1]:8080/socket.io/?sid=a%26b",
                "[::1]:8080",
                "[::1]:8080",
            ),
        ] {
            let mut request = reqwest::Request::new(reqwest::Method::GET, Url::parse(url).unwrap());
            request
                .headers_mut()
                .insert("x-api-key", header::HeaderValue::from_static("synthetic"));
            request.headers_mut().insert(
                header::PROXY_AUTHORIZATION,
                HeaderValue::from_static("proxy-only"),
            );
            let (authority, inner) = requests(request).unwrap();
            let connect = connect_request(&authority, None).unwrap();
            assert!(!inner.headers().contains_key(header::PROXY_AUTHORIZATION));
            assert_eq!(connect.method(), hyper::Method::CONNECT);
            assert_eq!(connect.uri().to_string(), connect_host);
            assert_eq!(connect.headers()[header::HOST], connect_host);
            assert_eq!(connect.headers().len(), 1);
            assert_eq!(inner.method(), hyper::Method::GET);
            assert_eq!(inner.uri().to_string(), "/socket.io/?sid=a%26b");
            assert_eq!(inner.headers()[header::HOST], inner_host);
            assert_eq!(inner.headers()["x-api-key"], "synthetic");
        }
    }
}
