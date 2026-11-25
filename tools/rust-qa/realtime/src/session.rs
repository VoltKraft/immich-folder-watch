use futures_util::{SinkExt, StreamExt};
use ifw_immich::realtime::{EnginePacket, polling_packets, websocket_packet};
use std::task::Poll;
use tokio::sync::{mpsc, watch};
use tokio::time::{Instant, timeout_at};
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::tungstenite::protocol::{CloseFrame, frame::coding::CloseCode};

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
    stopping: &mut watch::Receiver<bool>,
) -> Result<(), Error> {
    let connect_deadline = Instant::now() + CONNECT_TIMEOUT;
    let Some(opening) =
        until_stop(stopping, timeout_at(connect_deadline, transport.poll(None))).await
    else {
        return Ok(());
    };
    let body = opening??;
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
    let connect = session.namespace_packet("40");
    let Some(post) = until_stop(
        stopping,
        timeout_at(connect_deadline, session.send(connect)),
    )
    .await
    else {
        return Ok(());
    };
    post??;
    for packet in packets {
        timeout_at(
            connect_deadline,
            session.handle(packet.map_err(|_| Error::Protocol)?),
        )
        .await??;
    }
    drop(body);
    session.listen(connect_deadline, stopping).await?;
    if session.connected
        && let Err(error) = session.disconnect().await
    {
        observe(Observation::StopFailed(error));
    }
    Ok(())
}

async fn until_stop<T>(
    stopping: &mut watch::Receiver<bool>,
    operation: impl Future<Output = T>,
) -> Option<T> {
    tokio::select! {
        biased;
        _ = stopping.wait_for(|stopping| *stopping) => None,
        result = operation => Some(result),
    }
}

impl Session<'_> {
    fn namespace_packet(&self, kind: &str) -> String {
        if self.transport.namespace == "/" {
            kind.to_owned()
        } else {
            format!("{kind}{},", self.transport.namespace)
        }
    }

    async fn listen(
        &mut self,
        connect_deadline: Instant,
        stopping: &mut watch::Receiver<bool>,
    ) -> Result<(), Error> {
        if self.open.websocket && !self.upgrade(connect_deadline, stopping).await? {
            return Ok(());
        }
        loop {
            if !timeout_at(self.read_deadline(connect_deadline), self.receive(stopping)).await?? {
                return Ok(());
            }
        }
    }

    fn read_deadline(&self, connect_deadline: Instant) -> Instant {
        if self.connected {
            self.heartbeat
        } else {
            self.heartbeat.min(connect_deadline)
        }
    }

    async fn upgrade(
        &mut self,
        connect_deadline: Instant,
        stopping: &mut watch::Receiver<bool>,
    ) -> Result<bool, Error> {
        let deadline = Instant::now() + CONNECT_TIMEOUT;
        let sid = self.open.sid.clone();
        let probe = timeout_at(deadline, self.transport.probe(&sid));
        let mut probe_stop = stopping.clone();
        let observe = self.observe;
        let qualification = async {
            match until_stop(&mut probe_stop, probe).await {
                Some(Ok(Ok(ws))) => return Some(ws),
                Some(Ok(Err(error))) => observe(Observation::UpgradeDeclined(error)),
                Some(Err(_)) => observe(Observation::UpgradeDeclined(Error::Timeout)),
                None => {}
            }
            None
        };
        tokio::pin!(qualification);
        let socket = loop {
            // Pause new GETs as soon as the websocket probe succeeds.
            let ready =
                std::future::poll_fn(|cx| Poll::Ready(qualification.as_mut().poll(cx))).await;
            if let Poll::Ready(done) = ready {
                break done;
            }
            let poll = timeout_at(self.read_deadline(connect_deadline), self.receive(stopping));
            tokio::pin!(poll);
            tokio::select! {
                biased;
                // Poll this GET first so the other branch can only drain a
                // request already under way. Its reply can include a pong POST.
                active = &mut poll => if !active?? { return Ok(false); },
                done = &mut qualification => {
                    let active = if done.is_some() {
                        timeout_at(deadline, poll).await?
                    } else {
                        poll.await
                    };
                    if !active?? { return Ok(false); }
                    break done;
                }
            }
        };
        if *stopping.borrow() {
            return Ok(false);
        }
        if let Some(mut ws) = socket {
            timeout_at(deadline, ws.send(Message::text("5"))).await??;
            self.socket = Some(ws);
            observe(Observation::Upgraded);
        }
        Ok(true)
    }

    async fn disconnect(&mut self) -> Result<(), Error> {
        self.send(self.namespace_packet("41")).await?;
        if let Some(ws) = &mut self.socket {
            ws.close(Some(CloseFrame {
                code: CloseCode::Normal,
                reason: "io client disconnect".into(),
            }))
            .await?;
            while let Some(message) = ws.next().await {
                if matches!(message?, Message::Close(_)) {
                    return Ok(());
                }
            }
            return Err(Error::Disconnected);
        }
        Ok(())
    }

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

    /// Interrupt reads at shutdown. Finish any current write before issuing the
    /// disconnect, so the session cannot have two polling POSTs in flight.
    async fn receive(&mut self, stopping: &mut watch::Receiver<bool>) -> Result<bool, Error> {
        if let Some(ws) = &mut self.socket {
            let Some(frame) = until_stop(stopping, ws.next()).await else {
                return Ok(false);
            };
            match frame.ok_or(Error::Disconnected)?? {
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
            let Some(response) =
                until_stop(stopping, self.transport.poll(Some(&self.open.sid))).await
            else {
                return Ok(false);
            };
            for packet in polling_packets(&response?).map_err(|_| Error::Protocol)? {
                self.handle(packet.map_err(|_| Error::Protocol)?).await?;
            }
        }
        Ok(true)
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
