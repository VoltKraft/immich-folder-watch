# RW-02 realtime transport

The shipping adapter registers nine Immich events as requests to refresh remote
state. Its transport requires the configured origin, disables redirects, limits
each polling response or assembled WebSocket message to 4 MiB and stops new
reconnections before shutdown. A failed realtime session leaves periodic
inventory running. [Client](../../src/ImmichFolderWatch.Immich/ImmichRealtimeClient.cs)
and [transport](../../src/ImmichFolderWatch.Immich/ImmichRealtimeTransport.cs).

## Candidate source decision

On 2026-11-20 the published 0.6.0 archives were downloaded and read without
building or running their code. Both record upstream revision
`3434b654c18580785c0d0171bc1acbc0378580c7` and declare MIT in their manifests.

| Assessed archive | Local SHA-256 |
| --- | --- |
| [rust_socketio 0.6.0](https://static.crates.io/crates/rust_socketio/rust_socketio-0.6.0.crate) | `6a6a8672db895d567b3c0b8a4c0d3e98113ebb32badf6ce66004e743e5ee1e1e` |
| [rust_engineio 0.6.0](https://static.crates.io/crates/rust_engineio/rust_engineio-0.6.0.crate) | `d3d3572ceba6c5d79eecedf3be93640ca9512fa4100dff6a70f96c514adf4f1f` |

The Socket.IO builder creates the Engine.IO client internally and forwards
headers and a TLS connector. The polling adapter constructs its own reqwest
client with the default redirect policy. It yields chunks from each response
without enforcing the reference's cumulative limit. The secure WebSocket
constructor passes a default configuration to tokio-tungstenite. The public
builder has no injection point for the required transport policies. The
unmodified 0.6.0 client is therefore unsuitable for the candidate.
[Socket.IO builder](https://github.com/1c3t3a/rust-socketio/blob/3434b654c18580785c0d0171bc1acbc0378580c7/socketio/src/asynchronous/client/builder.rs),
[polling](https://github.com/1c3t3a/rust-socketio/blob/3434b654c18580785c0d0171bc1acbc0378580c7/engineio/src/asynchronous/async_transports/polling.rs)
and [WebSocket](https://github.com/1c3t3a/rust-socketio/blob/3434b654c18580785c0d0171bc1acbc0378580c7/engineio/src/asynchronous/async_transports/websocket_secure.rs).

## Implementation and gate

The [Rust framing module](../../rust/crates/ifw-immich/src/realtime.rs) decodes
Engine.IO polling record separators and WebSocket text packets. Its bounded
accumulator discards the entire body after an over-limit fragment. Higher
layers must validate the open handshake and Socket.IO JSON event structure
before forwarding a refresh request. Filesystem operations receive authority
from the subsequent complete inventory and their own policy checks.
[Engine.IO protocol](https://socket.io/docs/v4/engine-io-protocol/) and
[Socket.IO protocol](https://socket.io/docs/v4/socket-io-protocol/).

RW-02 still needs an audited HTTP, TLS and WebSocket stack and native sessions
with a synthetic server. Exercise authentication headers, origin and redirect
checks, namespace connect, polling, probe/upgrade, heartbeat, subscribed events,
fragmentation limits, reconnect cancellation and continued inventory polling
after disconnect. Frame tests alone cover only the protocol boundary.
