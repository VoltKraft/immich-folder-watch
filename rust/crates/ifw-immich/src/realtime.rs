//! Engine.IO v4 text framing shared by the polling and WebSocket transports.
//! A Socket.IO event only tells the worker to refresh authorized remote state.

/// The reference applies this ceiling to an entire polling response or an
/// entire reassembled WebSocket message, including framing.
pub const MAX_MESSAGE_BYTES: usize = 4 * 1024 * 1024;

#[derive(Debug, Eq, PartialEq)]
pub enum FrameError {
    TooLarge,
    InvalidUtf8,
    InvalidPacket,
}

/// Accumulate transport fragments before handing a complete message to the
/// protocol. Once a fragment exceeds the bound, the whole message is rejected.
#[derive(Default)]
pub struct IncomingMessage {
    bytes: Vec<u8>,
    rejected: bool,
}

impl IncomingMessage {
    pub fn append(&mut self, chunk: &[u8]) -> Result<(), FrameError> {
        if self.rejected {
            return Err(FrameError::TooLarge);
        }
        if chunk.len() > MAX_MESSAGE_BYTES - self.bytes.len() {
            self.bytes = Vec::new();
            self.rejected = true;
            return Err(FrameError::TooLarge);
        }
        self.bytes.extend_from_slice(chunk);
        Ok(())
    }

    pub fn finish(self) -> Result<Vec<u8>, FrameError> {
        if self.rejected {
            Err(FrameError::TooLarge)
        } else {
            Ok(self.bytes)
        }
    }
}

#[derive(Debug, Eq, PartialEq)]
pub enum EnginePacket<'a> {
    Open(&'a str),
    Close,
    Ping(&'a str),
    Pong(&'a str),
    Message(&'a str),
    Upgrade,
    Noop,
    PollingBinaryBase64(&'a str),
}

/// HTTP payloads carry one or more record-separated packets. Decode an HTTP
/// response only after the transport has received and bounded its whole body.
pub fn polling_packets(
    bytes: &[u8],
) -> Result<impl Iterator<Item = Result<EnginePacket<'_>, FrameError>>, FrameError> {
    Ok(bounded_text(bytes)?
        .split('\u{1e}')
        .map(|packet| decode(packet, true)))
}

/// Each WebSocket text message carries a single Engine.IO packet.
pub fn websocket_packet(bytes: &[u8]) -> Result<EnginePacket<'_>, FrameError> {
    decode(bounded_text(bytes)?, false)
}

fn bounded_text(bytes: &[u8]) -> Result<&str, FrameError> {
    if bytes.len() > MAX_MESSAGE_BYTES {
        return Err(FrameError::TooLarge);
    }
    std::str::from_utf8(bytes).map_err(|_| FrameError::InvalidUtf8)
}

fn decode(text: &str, polling: bool) -> Result<EnginePacket<'_>, FrameError> {
    let (kind, data) = text.split_at_checked(1).ok_or(FrameError::InvalidPacket)?;
    match (kind, data) {
        ("0", data) if !data.is_empty() => Ok(EnginePacket::Open(data)),
        ("1", "") => Ok(EnginePacket::Close),
        ("2", data) => Ok(EnginePacket::Ping(data)),
        ("3", data) => Ok(EnginePacket::Pong(data)),
        ("4", data) => Ok(EnginePacket::Message(data)),
        ("5", "") => Ok(EnginePacket::Upgrade),
        ("6", "") => Ok(EnginePacket::Noop),
        ("b", data) if polling => Ok(EnginePacket::PollingBinaryBase64(data)),
        _ => Err(FrameError::InvalidPacket),
    }
}

/// Names are case-sensitive and match the shipping Immich adapter's subscriptions.
pub fn signals_remote_change(event: &str) -> bool {
    matches!(
        event,
        "on_upload_success"
            | "on_asset_trash"
            | "on_asset_delete"
            | "on_asset_update"
            | "on_asset_restore"
            | "on_album_create"
            | "on_album_update"
            | "on_album_delete"
            | "on_album_invite"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn polling_holds_multiple_packets_and_websocket_preserves_the_message_boundary() {
        let body = b"40\x1e42[\"on_album_update\",{}]\x1e2";
        let result = polling_packets(body)
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        assert_eq!(
            result,
            [
                EnginePacket::Message("0"),
                EnginePacket::Message("2[\"on_album_update\",{}]"),
                EnginePacket::Ping("")
            ]
        );
        assert_eq!(websocket_packet(b"2probe"), Ok(EnginePacket::Ping("probe")));
        assert_eq!(websocket_packet(b"3probe"), Ok(EnginePacket::Pong("probe")));
        assert_eq!(websocket_packet(b"5"), Ok(EnginePacket::Upgrade));
    }

    #[test]
    fn unknown_packets_and_partial_records_are_errors() {
        for frame in [
            b"".as_slice(),
            b"0",
            b"6x",
            b"unrecognized",
            b"beA==",
            "🎞".as_bytes(),
        ] {
            assert_eq!(websocket_packet(frame), Err(FrameError::InvalidPacket));
        }
        assert_eq!(websocket_packet(&[0xff]), Err(FrameError::InvalidUtf8));
        let mut parts = polling_packets(b"beA==\x1e").unwrap();
        assert_eq!(
            parts.next(),
            Some(Ok(EnginePacket::PollingBinaryBase64("eA==")))
        );
        assert_eq!(parts.next(), Some(Err(FrameError::InvalidPacket)));
    }

    #[test]
    fn a_fragment_over_the_limit_discards_the_entire_message() {
        let large = vec![1; MAX_MESSAGE_BYTES];
        let mut exact = IncomingMessage::default();
        exact.append(&large).unwrap();
        assert_eq!(exact.finish().unwrap().len(), MAX_MESSAGE_BYTES);
        let mut partial = IncomingMessage::default();
        partial.append(&large).unwrap();
        assert_eq!(partial.append(b"x"), Err(FrameError::TooLarge));
        assert_eq!(partial.append(b""), Err(FrameError::TooLarge));
        assert_eq!(partial.finish(), Err(FrameError::TooLarge));
    }
}
