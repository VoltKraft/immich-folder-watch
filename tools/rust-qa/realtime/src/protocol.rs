//! Socket.IO v5 data consumed by the Immich subscriptions.

use ifw_immich::realtime::{MAX_MESSAGE_BYTES, signals_remote_change};
use serde::Deserialize;
use serde::de::{Error as _, IgnoredAny, SeqAccess, Visitor};
use std::fmt;
use std::time::Duration;

use crate::Error;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Open {
    pub sid: String,
    #[serde(rename = "upgrades", deserialize_with = "advertises_websocket")]
    pub websocket: bool,
    ping_interval: u64,
    ping_timeout: u64,
    pub max_payload: usize,
}

impl Open {
    pub fn parse(text: &str) -> Result<Self, Error> {
        // The packet type occupies one byte of the message ceiling.
        if text.len() >= MAX_MESSAGE_BYTES {
            return Err(Error::Limit);
        }
        let value: Self = serde_json::from_str(text).map_err(|_| Error::Protocol)?;
        if value.sid.is_empty()
            || value.ping_interval == 0
            || value.ping_timeout == 0
            || value.max_payload == 0
        {
            return Err(Error::Protocol);
        }
        Ok(value)
    }

    pub fn heartbeat_window(&self) -> Duration {
        Duration::from_millis(self.ping_interval.saturating_add(self.ping_timeout))
            .min(Duration::from_secs(120))
    }
}

fn advertises_websocket<'de, D: serde::Deserializer<'de>>(de: D) -> Result<bool, D::Error> {
    struct Upgrades;
    impl<'de> Visitor<'de> for Upgrades {
        type Value = bool;
        fn expecting(&self, fmt: &mut fmt::Formatter<'_>) -> fmt::Result {
            fmt.write_str("an array of Engine.IO transport names")
        }
        fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<bool, A::Error> {
            let mut websocket = false;
            while let Some(name) = seq.next_element::<String>()? {
                websocket |= name.eq_ignore_ascii_case("websocket");
            }
            Ok(websocket)
        }
    }
    de.deserialize_seq(Upgrades)
}

#[derive(Deserialize)]
struct NamespaceAck {
    sid: String,
}

/// Only the event name goes to the subscription table. Still consume the entire
/// JSON sequence so malformed trailing data cannot schedule a refresh.
struct EventName(String);

impl<'de> Deserialize<'de> for EventName {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct EventVisitor;
        impl<'de> Visitor<'de> for EventVisitor {
            type Value = EventName;
            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("a Socket.IO event array beginning with a string")
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Self::Value, A::Error> {
                let name = seq
                    .next_element()?
                    .ok_or_else(|| A::Error::custom("missing name"))?;
                while seq.next_element::<IgnoredAny>()?.is_some() {}
                Ok(EventName(name))
            }
        }
        deserializer.deserialize_seq(EventVisitor)
    }
}

pub(crate) enum Action {
    Connected,
    ServerDisconnected,
    Refresh,
    Ignore,
}

pub(crate) fn socket_packet(raw: &str, namespace: &str, connected: bool) -> Result<Action, Error> {
    let (kind, rest) = raw.split_at_checked(1).ok_or(Error::Protocol)?;
    // Binary event/ack packets carry an attachment count before the namespace.
    // Immich's subscribed messages are JSON events, never attachment data.
    if matches!(kind, "5" | "6") {
        return Ok(Action::Ignore);
    }
    let (received_ns, data) = if rest.starts_with('/') {
        rest.split_once(',').ok_or(Error::Protocol)?
    } else {
        ("/", rest)
    };
    if received_ns != namespace {
        return Ok(Action::Ignore);
    }
    match kind {
        "0" if !connected => {
            let ack: NamespaceAck = serde_json::from_str(data).map_err(|_| Error::Protocol)?;
            if ack.sid.is_empty() {
                Err(Error::Protocol)
            } else {
                Ok(Action::Connected)
            }
        }
        "1" if connected && data.is_empty() => Ok(Action::ServerDisconnected),
        "1" | "4" => Err(Error::Disconnected),
        "2" if connected => {
            let json = data.trim_start_matches(|c: char| c.is_ascii_digit());
            let event: EventName = serde_json::from_str(json).map_err(|_| Error::Protocol)?;
            Ok(if signals_remote_change(&event.0) {
                Action::Refresh
            } else {
                Action::Ignore
            })
        }
        "3" if connected => Ok(Action::Ignore),
        _ => Err(Error::Protocol),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_complete_subscribed_events_on_a_connected_namespace_request_refresh() {
        assert!(matches!(
            socket_packet(
                r#"2/selected,9["on_album_update",{"name":"🎞"}]"#,
                "/selected",
                true
            ),
            Ok(Action::Refresh)
        ));
        assert!(matches!(
            socket_packet(r#"2/other,["on_album_update"]"#, "/selected", true),
            Ok(Action::Ignore)
        ));
        assert!(matches!(
            socket_packet(r#"2["on_album_update",{}]extra"#, "/", true),
            Err(Error::Protocol)
        ));
        assert!(matches!(
            socket_packet(r#"2["on_album_update",{"unfinished":]"#, "/", true),
            Err(Error::Protocol)
        ));
        assert!(matches!(
            socket_packet(r#"2["on_album_update"]"#, "/", false),
            Err(Error::Protocol)
        ));
        assert!(matches!(
            socket_packet(r#"0{"sid":""}"#, "/", false),
            Err(Error::Protocol)
        ));
    }

    #[test]
    fn handshake_limits_and_server_heartbeat_deadlines_are_finite() {
        assert!(matches!(
            Open::parse(&"a".repeat(MAX_MESSAGE_BYTES)),
            Err(Error::Limit)
        ));
        let open = Open::parse(r#"{"sid":"eio","upgrades":[],"pingInterval":18446744073709551615,"pingTimeout":20,"maxPayload":4096}"#).unwrap();
        assert_eq!(open.heartbeat_window(), Duration::from_secs(120));
    }
}
