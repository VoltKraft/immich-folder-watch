use std::time::Duration;

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

impl Transport {
    pub fn new(
        api: Url,
        allow_http: bool,
        api_key: &str,
        roots: Option<Vec<Certificate>>,
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

    pub async fn probe(&self, sid: &str) -> Result<Socket, Error> {
        // Keep the exact origin, headers, TLS verifier and no-redirect policy of
        // polling. Only switch the I/O stream after the RFC 6455 response.
        let key = generate_key();
        let accept = derive_accept_key(key.as_bytes());
        let resp = self
            .request(Method::GET, self.uri("websocket", Some(sid)))?
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
        let mut ws =
            Socket::from_raw_socket(resp.upgrade().await?, Role::Client, Some(config)).await;
        ws.send(Message::text("2probe")).await?;
        loop {
            match ws.next().await.ok_or(Error::Disconnected)?? {
                Message::Text(text) if text == "3probe" => return Ok(ws),
                Message::Ping(_) => ws.flush().await?,
                Message::Pong(_) => {}
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
            tungstenite::Error::ConnectionClosed | tungstenite::Error::AlreadyClosed => {
                Self::Disconnected
            }
            _ => Self::Transport,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn authenticated_requests_require_the_configured_scheme_host_port_and_no_user_info() {
        let _ = rustls::crypto::ring::default_provider().install_default();
        let api = Url::parse("https://127.0.0.1:4443/collection/api").unwrap();
        let transport = Transport::new(api, false, "synthetic", Some(Vec::new())).unwrap();
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
}
