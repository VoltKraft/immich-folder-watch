//! Loopback-only RW-02 harness for the actual Rust network adapter.
#![forbid(unsafe_code)]

mod protocol;
mod session;
mod transport;

use reqwest::{Certificate, Url};
use std::{
    cell::Cell,
    net::{IpAddr, SocketAddr},
    path::Path,
    process::ExitCode,
    time::Duration,
};
use tokio::sync::{mpsc, watch};
use tokio::time::{self, Instant, MissedTickBehavior};
use transport::Transport;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Error {
    Origin,
    Transport,
    Status(u16),
    Protocol,
    Limit,
    Timeout,
    Disconnected,
    PeerClosed,
}

impl From<time::error::Elapsed> for Error {
    fn from(_: time::error::Elapsed) -> Self {
        Self::Timeout
    }
}

#[derive(Clone, Copy, Debug)]
enum Observation {
    Attempt,
    Connected,
    ServerDisconnected,
    PeerClosed,
    Upgraded,
    DirectWebSocket,
    UpgradeDeclined(Error),
    Heartbeat,
    Event,
    Periodic,
    Lost(Error),
    StopFailed(Error),
    Inventory,
    Stopped,
}

impl Observation {
    fn print(self) {
        match self {
            Self::Lost(e) => println!("Lost {e:?}"),
            Self::StopFailed(e) => println!("StopFailed {e:?}"),
            Self::UpgradeDeclined(e) => println!("UpgradeDeclined {e:?}"),
            other => println!("{other:?}"),
        }
    }
}

async fn supervise(
    transport: &Transport,
    refresh: &mpsc::Sender<()>,
    shutdown: impl Future<Output = ()>,
    initial_retry: Duration,
    inventory_period: Duration,
    observe: session::Observe<'_>,
) {
    tokio::pin!(shutdown);
    let mut interval = time::interval_at(Instant::now() + inventory_period, inventory_period);
    interval.set_missed_tick_behavior(MissedTickBehavior::Skip);
    let retry = Cell::new(Some(initial_retry));
    let report = |event| {
        match event {
            Observation::Connected => retry.set(Some(initial_retry)),
            Observation::ServerDisconnected | Observation::PeerClosed => retry.set(None),
            _ => {}
        }
        observe(event);
    };
    let (request_stop, mut stopping) = watch::channel(false);
    let connection = async {
        let mut prefer_websocket = false;
        loop {
            report(Observation::Attempt);
            let Err(error) = session::run(
                transport,
                refresh,
                &report,
                &mut stopping,
                &mut prefer_websocket,
            )
            .await
            else {
                return;
            };
            report(Observation::Lost(error));
            let Some(delay) = retry.get() else {
                return;
            };
            tokio::select! {
                biased;
                _ = stopping.wait_for(|stopping| *stopping) => return,
                _ = time::sleep(delay) => {}
            }
            retry.set(Some((delay * 2).min(Duration::from_secs(30))));
        }
    };
    tokio::pin!(connection);
    let mut connection_finished = false;
    loop {
        tokio::select! {
            biased;
            _ = &mut shutdown => break,
            _ = interval.tick() => { let _ = refresh.try_send(()); observe(Observation::Periodic); }
            _ = &mut connection, if !connection_finished => connection_finished = true,
        }
    }
    let _ = request_stop.send(true);
    if !connection_finished
        && time::timeout(Duration::from_secs(2), connection)
            .await
            .is_err()
    {
        observe(Observation::StopFailed(Error::Timeout));
    }
    observe(Observation::Stopped);
}

fn interval(value: &str) -> Result<Duration, Error> {
    value
        .parse::<u64>()
        .ok()
        .filter(|n| (1..=30_000).contains(n))
        .map(Duration::from_millis)
        .ok_or(Error::Protocol)
}

fn fixture_roots(source: &str) -> Result<Option<Vec<Certificate>>, Error> {
    if source == "linux-platform" {
        // With both OpenSSL paths set, the pinned Linux verifier loads only
        // the child process's fixture store. Other hosts use explicit roots.
        if !cfg!(target_os = "linux")
            || std::env::var("SSL_CERT_FILE").as_deref() != Ok("root.pem")
            || std::env::var("SSL_CERT_DIR").as_deref() != Ok("certs")
        {
            return Err(Error::Protocol);
        }
        return Ok(None);
    }
    if source == "-" {
        return Ok(Some(Vec::new()));
    }
    let pem = std::fs::read(Path::new(source)).map_err(|_| Error::Transport)?;
    Ok(Some(vec![
        Certificate::from_pem(&pem).map_err(|_| Error::Transport)?,
    ]))
}

fn fixture_https_proxy(
    api: &Url,
    expected: &str,
    read: impl Fn(&str) -> Option<String>,
) -> Result<Option<Url>, Error> {
    if !cfg!(target_os = "linux") || api.scheme() != "https" {
        return Err(Error::Protocol);
    }
    let address = expected
        .strip_prefix("http://")
        .and_then(|s| s.parse::<SocketAddr>().ok())
        .filter(|addr| addr.ip().is_loopback() && addr.port() != 0)
        .ok_or(Error::Protocol)?;
    let owned = Url::parse(&format!("http://{address}")).map_err(|_| Error::Protocol)?;
    let proxy = transport::LinuxHttpsProxy::from_environment(api, read);
    if proxy
        .endpoint
        .as_ref()
        .is_some_and(|selected| selected != &owned)
    {
        return Err(Error::Protocol);
    }
    Ok(proxy.route())
}

async fn probe(args: &[String]) -> Result<(), Error> {
    let [url, mode, root, budget, retry, period, extra @ ..] = args else {
        return Err(Error::Protocol);
    };
    let url = Url::parse(url).map_err(|_| Error::Origin)?;
    if !url
        .host_str()
        .and_then(|h| h.trim_matches(['[', ']']).parse::<IpAddr>().ok())
        .is_some_and(|addr| addr.is_loopback())
    {
        return Err(Error::Origin);
    }
    let (allow_http, proxy) = match (mode.as_str(), extra) {
        ("https", []) => (false, None),
        ("allow-http", []) => (true, None),
        ("https-linux-proxy", [owned]) => (
            false,
            fixture_https_proxy(&url, owned, |key| std::env::var(key).ok())?,
        ),
        _ => return Err(Error::Protocol),
    };
    let transport = Transport::new(url, allow_http, "synthetic", fixture_roots(root)?, proxy)?;
    let (refresh, mut rx) = mpsc::channel(1);
    let inventory = async {
        while rx.recv().await.is_some() {
            if transport.fixture_inventory().await.is_ok() {
                Observation::Inventory.print();
            }
        }
    };
    tokio::select! {
        biased;
        _ = supervise(&transport, &refresh, time::sleep(interval(budget)?), interval(retry)?, interval(period)?, &Observation::print) => {}
        () = inventory => return Err(Error::Disconnected)
    }
    Ok(())
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> ExitCode {
    if rustls::crypto::ring::default_provider()
        .install_default()
        .is_err()
    {
        eprintln!("The selected TLS provider could not be installed.");
        return ExitCode::FAILURE;
    }
    match probe(&std::env::args().skip(1).collect::<Vec<_>>()).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error:?}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;

    #[test]
    fn selected_proxy_must_match_the_owned_numeric_loopback_even_when_bypassed() {
        let api = Url::parse("https://127.0.0.1:8000/collection/api").unwrap();
        let owned = "http://127.0.0.1:8001";
        for unowned in [
            "http://127.0.0.1:8002",
            "http://other.invalid:8001",
            "http://someone@127.0.0.1:8001",
            "https://127.0.0.1:8001",
        ] {
            assert_eq!(
                fixture_https_proxy(&api, owned, |key| match key {
                    "HTTPS_PROXY" => Some(unowned.into()),
                    "NO_PROXY" => Some("127.0.0.1".into()),
                    _ => None,
                }),
                Err(Error::Protocol)
            );
        }
        for invalid in [
            "http://localhost:8001",
            "http://192.0.2.1:8001",
            "http://[::1]:0",
            "http://127.0.0.1:8001/path",
            "http://127.0.0.1:8001?query",
        ] {
            assert_eq!(
                fixture_https_proxy(&api, invalid, |_| None),
                Err(Error::Protocol)
            );
        }
    }
}
