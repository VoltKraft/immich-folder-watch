//! Loopback-only RW-02 harness for the actual Rust network adapter.
#![forbid(unsafe_code)]

mod protocol;
mod session;
mod transport;

use reqwest::{Certificate, Url};
use std::{cell::Cell, net::IpAddr, path::Path, process::ExitCode, time::Duration};
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
    Upgraded,
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
            Observation::ServerDisconnected => retry.set(None),
            _ => {}
        }
        observe(event);
    };
    let (request_stop, mut stopping) = watch::channel(false);
    let connection = async {
        loop {
            report(Observation::Attempt);
            let Err(error) = session::run(transport, refresh, &report, &mut stopping).await else {
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

async fn probe(args: &[String]) -> Result<(), Error> {
    let [url, mode, root, budget, retry, period] = args else {
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
    let allow_http = match mode.as_str() {
        "https" => false,
        "allow-http" => true,
        _ => return Err(Error::Protocol),
    };
    // The fixture always supplies isolated trust, including an empty store
    // when testing rejection. Never open a user's certificate store here.
    let mut roots = Vec::new();
    if root != "-" {
        let pem = std::fs::read(Path::new(root)).map_err(|_| Error::Transport)?;
        roots.push(Certificate::from_pem(&pem).map_err(|_| Error::Transport)?);
    }
    let transport = Transport::new(url, allow_http, "synthetic", Some(roots))?;
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
