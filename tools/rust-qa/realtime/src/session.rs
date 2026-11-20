use futures_util::{SinkExt, StreamExt};
use ifw_immich::realtime::{EnginePacket, polling_packets, websocket_packet};
use tokio::sync::mpsc;
use tokio::time::{Instant, timeout_at};
use tokio_tungstenite::tungstenite::Message;

use crate::protocol::{Action, Open, socket_packet};
use crate::transport::{CONNECT_TIMEOUT, Socket, Transport};
use crate::{Error, Observation};

pub(crate) type Observe<'a> = &'a dyn Fn(Observation);

struct Session<'a> {
    transport: &'a Transport,
    open: Open,
    socket: Option<Socket>,
    heartbeat: Instant,
    connected: bool,
    refresh: &'a mpsc::Sender<()>,
    observe: Observe<'a>,
}

pub(crate) async fn run(
    transport: &Transport,
    refresh: &mpsc::Sender<()>,
    observe: Observe<'_>,
) -> Result<(), Error> {
    let connect_deadline = Instant::now() + CONNECT_TIMEOUT;
    let body = timeout_at(connect_deadline, transport.poll(None)).await??;
    let mut packets = polling_packets(&body).map_err(|_| Error::Protocol)?;
    let Some(Ok(EnginePacket::Open(text))) = packets.next() else {
        return Err(Error::Protocol);
    };
    let open = Open::parse(text)?;
    let mut session = Session {
        transport,
        heartbeat: Instant::now() + open.heartbeat_window(),
        open,
        socket: None,
        connected: false,
        refresh,
        observe,
    };
    let connect = if transport.namespace == "/" {
        "40".to_owned()
    } else {
        format!("40{},", transport.namespace)
    };
    timeout_at(connect_deadline, session.send(connect)).await??;
    for packet in packets {
        timeout_at(
            connect_deadline,
            session.handle(packet.map_err(|_| Error::Protocol)?),
        )
        .await??;
    }
    drop(body);
    while !session.connected {
        timeout_at(connect_deadline.min(session.heartbeat), session.receive()).await??;
    }
    if session.open.websocket {
        // There is no GET or POST in flight. A failure before "5" still owns
        // the polling transport. After "5", reconnect on uncertainty.
        let deadline = session.heartbeat.min(Instant::now() + CONNECT_TIMEOUT);
        match timeout_at(deadline, transport.probe(&session.open.sid)).await {
            Ok(Ok(mut ws)) => {
                timeout_at(deadline, ws.send(Message::text("5"))).await??;
                session.socket = Some(ws);
                observe(Observation::Upgraded);
            }
            Ok(Err(err)) => observe(Observation::UpgradeDeclined(err)),
            Err(_) => observe(Observation::UpgradeDeclined(Error::Timeout)),
        }
    }
    loop {
        timeout_at(session.heartbeat, session.receive()).await??;
    }
}

impl Session<'_> {
    async fn send(&mut self, text: String) -> Result<(), Error> {
        if let Some(ws) = &mut self.socket {
            ws.send(Message::text(text)).await?;
            Ok(())
        } else {
            self.transport
                .post(&self.open.sid, text, self.open.max_payload)
                .await
        }
    }

    async fn receive(&mut self) -> Result<(), Error> {
        if let Some(ws) = &mut self.socket {
            match ws.next().await.ok_or(Error::Disconnected)?? {
                Message::Text(text) => {
                    self.handle(websocket_packet(text.as_bytes()).map_err(|_| Error::Protocol)?)
                        .await?
                }
                Message::Close(_) => return Err(Error::Disconnected),
                Message::Ping(_) => ws.flush().await?,
                Message::Binary(_) | Message::Pong(_) => {}
                Message::Frame(_) => return Err(Error::Protocol),
            }
        } else {
            let body = self.transport.poll(Some(&self.open.sid)).await?;
            for packet in polling_packets(&body).map_err(|_| Error::Protocol)? {
                self.handle(packet.map_err(|_| Error::Protocol)?).await?;
            }
        }
        Ok(())
    }

    async fn handle(&mut self, packet: EnginePacket<'_>) -> Result<(), Error> {
        match packet {
            EnginePacket::Ping(payload) => {
                self.send(format!("3{payload}")).await?;
                self.heartbeat = Instant::now() + self.open.heartbeat_window();
                (self.observe)(Observation::Heartbeat);
            }
            EnginePacket::Message(data) => {
                match socket_packet(data, &self.transport.namespace, self.connected)? {
                    Action::Connected => {
                        self.connected = true;
                        (self.observe)(Observation::Connected);
                    }
                    Action::Refresh => {
                        let _ = self.refresh.try_send(());
                        (self.observe)(Observation::Event);
                    }
                    Action::Ignore => {}
                }
            }
            EnginePacket::Close => return Err(Error::Disconnected),
            EnginePacket::Noop | EnginePacket::Pong(_) | EnginePacket::PollingBinaryBase64(_) => {}
            EnginePacket::Open(_) | EnginePacket::Upgrade => return Err(Error::Protocol),
        }
        Ok(())
    }
}
