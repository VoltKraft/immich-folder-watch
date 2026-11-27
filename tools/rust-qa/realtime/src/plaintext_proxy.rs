//! A plaintext WebSocket uses an unauthenticated CONNECT to the configured
//! proxy, followed by the normal authenticated HTTP upgrade inside the tunnel.

use hyper::{HeaderMap, Request, StatusCode, Uri, client::conn::http1};
use hyper_util::rt::TokioIo;
use reqwest::{Body, Upgraded, Url, header};
use tokio::{
    io::{AsyncRead, AsyncWrite},
    net::TcpStream,
};

use crate::{Error, transport::validate_upgrade};

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

fn requests(request: reqwest::Request) -> Result<(Request<Body>, Request<Body>), Error> {
    let url = request.url();
    if url.scheme() != "http" || !url.username().is_empty() || url.password().is_some() {
        return Err(Error::Origin);
    }
    let host = url.host_str().ok_or(Error::Origin)?;
    // CONNECT uses authority-form, including the port even for the default 80.
    let destination = format!(
        "{host}:{}",
        url.port_or_known_default().ok_or(Error::Origin)?
    );
    let authority = Uri::builder()
        .authority(destination.as_str())
        .build()
        .map_err(|_| Error::Origin)?;
    let connect = Request::connect(authority)
        .header(header::HOST, destination)
        .body(Body::default())
        .map_err(|_| Error::Origin)?;

    let mut inner: Request<Body> = request.try_into()?;
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
    Ok((connect, inner))
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

pub(crate) async fn websocket(
    relay: &Url,
    request: reqwest::Request,
    accept: &str,
) -> Result<Upgraded, Error> {
    let (connect, inner) = requests(request)?;
    let stream = TcpStream::connect(relay_address(relay)?)
        .await
        .map_err(|_| Error::Transport)?;
    let tunnel = upgrade(stream, connect, |status, _| {
        if status.is_success() {
            Ok(())
        } else {
            Err(Error::Status(status.as_u16()))
        }
    })
    .await?;
    upgrade(tunnel, inner, |status, headers| {
        validate_upgrade(status, headers, accept)
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

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
            let (connect, inner) = requests(request).unwrap();
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
