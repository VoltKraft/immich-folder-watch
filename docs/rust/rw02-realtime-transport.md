# RW-02 native realtime transport

The standalone [assessment workspace](../../tools/rust-qa/realtime/README.md)
implements the subscribed Immich Socket.IO path in Rust. Its release executable
connects only to numeric loopback addresses and uses freshly generated trust
material. The C# application and the rejected off-the-shelf Socket.IO client
are absent from its process. Product dependencies remain subject to the RW-02
stage decision. [Earlier transport comparison](rw02-realtime.md).

## Wire contract

The reference sends the API key in a request header. The application removes
a terminal `api` path component. SocketIOClient 4.0.5 treats the remaining
non-root path as a Socket.IO namespace. Its independent Engine.IO HTTP path
defaults to `/socket.io/`. The probe exercises both `/api` and
`/collection/api`. [Shipping client](../../src/ImmichFolderWatch.Immich/ImmichRealtimeClient.cs),
[pinned namespace implementation](https://github.com/doghappy/socket.io-client-csharp/blob/9deebcfe8079164d269ec4f22ba58589366014fb/src/SocketIOClient/SocketIO.cs)
and [pinned request builder](https://github.com/doghappy/socket.io-client-csharp/blob/9deebcfe8079164d269ec4f22ba58589366014fb/src/SocketIOClient/Session/SessionBase.cs).

The Rust client opens an Engine.IO polling session, parses and bounds its
handshake, posts the namespace CONNECT and verifies the server's separate
Socket.IO session ID. All requests derive from one configured origin. A single
HTTP/1 client checks that origin before attaching the sensitive fixture
header. It disables redirects, automatic retries and proxies. HTTPS is the
default, with an explicit HTTP exception. TLS verifies chain and hostname.
The fixture substitutes a private root store. [HTTP and TLS transport](../../tools/rust-qa/realtime/src/transport.rs).

For an advertised WebSocket upgrade, the client checks the HTTP 101 response,
the Connection and Upgrade fields, and the RFC 6455 challenge. Unrequested
extensions or subprotocols fail negotiation. The same HTTP/TLS connection
becomes a bounded tokio-tungstenite stream. The client exchanges
`2probe`/`3probe` before sending `5`. A refused probe leaves polling usable.
An uncertain final upgrade write ends the session. A server heartbeat determines
the next deadline, capped at 120 seconds. The initial handshake and the upgrade
have ten-second ceilings. Shutdown cancels an outstanding read or reconnect delay
and gives an established session two seconds to disconnect on its active
transport. Delays between attempts grow to a maximum of 30 seconds. [Session](../../tools/rust-qa/realtime/src/session.rs),
[Engine.IO](https://socket.io/docs/v4/engine-io-protocol/) and
[Socket.IO](https://socket.io/docs/v4/socket-io-protocol/).

The HTTP reader bounds both declared and streamed bodies at 4 MiB. WebSocket
frame and reassembled message limits are both 4 MiB. The application framing
crate decodes bounded messages. Only complete JSON events in the acknowledged
namespace can request refresh. Event payloads do not grant file or album
authority. One queued wakeup suffices for overlapping events and periodic
ticks. The fixture consumer performs an authenticated HTTP read of its
synthetic empty album inventory. [Framing](../../rust/crates/ifw-immich/src/realtime.rs)
and [Socket.IO parser](../../tools/rust-qa/realtime/src/protocol.rs).

### Escaped API paths and Socket.IO namespaces

The shipping client takes the normalized `System.Uri.AbsolutePath` before
stripping a terminal `api` component case-insensitively. Before the correction,
Rust copied the original percent escapes into the namespace. For
`/%63ollection/api` it sent `40/%63ollection,` to a peer listening on
`/collection`. That peer received two Rust connection attempts and delivered
no event. The signed client sent `40/collection,` and received the event on its
first connection. The same mismatch affected `/collection/%61pi` and `/%61pi`.
[Shipping namespace construction](../../src/ImmichFolderWatch.Immich/ImmichRealtimeClient.cs) ·
[Rust endpoint construction](../../tools/rust-qa/realtime/src/transport.rs).

The paired Fedora x64 check ran the Rust executable and the signed 3.0.4
Linux x64 Flatpak's original realtime and album clients on ten synthetic
loopback URLs each. Both clients received an event, issued the same
authenticated album GET and sent the expected disconnect for each URL. The
inputs covered plain and escaped root and named paths, a mixed-case terminal
API component, a space, raw and escaped UTF-8, an escaped slash and a
double-encoded slash. The signed OSTree commit was
`abeebe13b83cc4b8246fb4a8715daddce7f3dd4bf52861ae4ca33b06755104da`.
The paired wire record has SHA-256
`01ac25d9ccea6b491abbc0adb42aba7300b610a169be913cfa8c81c3e46e57d6`.
[Shipping album request](../../src/ImmichFolderWatch.Immich/ImmichAssetClient.cs).

Two cases now run in the regular transport suite. The polling peer requires
these exact packets and HTTP paths. The Engine.IO endpoint is `/socket.io/`
in both cases.

| Configured API path | Socket.IO CONNECT and DISCONNECT | Album GET path |
| --- | --- | --- |
| `/%61pi` | `40`, `41` | `/api/albums` |
| `/%63ollection/caf%c3%a9/%7esummer%2fphotos/%61PI` | `40/collection/caf%C3%A9/~summer%2fphotos,`, `41/collection/caf%C3%A9/~summer%2fphotos,` | `/collection/caf%C3%A9/~summer%2fphotos/aPI/albums` |

The native Fedora x64 run passed all 22 wire scenarios and four Rust unit
tests. Its session record has SHA-256
`aff962d22265f3e14f4a6d361006ea8e4b3d92a7505217fb63d042ae80486d51`.
The earlier four-target run at `e2f161b` exercised the original 20 scenarios.
[Strict peers](../../tools/rust-qa/realtime/verify.py) ·
[Earlier native results](#four-native-transport-results-at-e2f161b).

At `6cd7757` native Ubuntu x64 and ARM64 each passed all 22 scenarios
and four unit tests. The original archives matched their GitHub digests.
On each host, all 19 recorded source inputs matched Git, and all ten indexed
outputs matched their receipt. For the escaped root the peer received
`41`. The named case ended with `41/collection/caf%C3%A9/~summer%2fphotos,`.
[Ubuntu x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15210518870) ·
[Ubuntu ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15210644228).

Windows x64 and ARM64 also passed the 22 cases and four unit tests at
`6cd7757`. Independent replay checked all four native archives, each
target graph, 19 source inputs and ten raw output hashes per target.
Across the four hosts, 88 wire cases and 16 unit tests passed. The Windows
x64 archive has SHA-256 `dd77b477436e841045fd3a9c06b317507c0ad5058be89c667f43c2f1105ec758`.
[Windows x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15215793491) ·
[Windows ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46021242330/artifacts/15215586046).

### Server ends the selected namespace

On Fedora x64 a loopback peer acknowledged a subscription, delivered one
album event and then explicitly ended the selected Socket.IO namespace.
With both the default namespace and `/collection`, the signed 3.0.4
client opened one session. The earlier Rust client opened a second one and
delivered another refresh. The shipping client removes its subscriptions
on a server namespace disconnect. Periodic inventory remains available.
[Shipping client](../../src/ImmichFolderWatch.Immich/ImmichRealtimeClient.cs) ·
[Pinned Socket.IO disconnect handler](https://github.com/doghappy/socket.io-client-csharp/blob/9deebcfe8079164d269ec4f22ba58589366014fb/src/SocketIOClient/SocketIO.cs#L444-L469).

The corrected Rust client kept one session on both transports, ignored
later events and sent its final namespace disconnect on the original
session. Both clients continued answering Engine.IO pings on polling.
On the detached WebSocket both sent the client's disconnect followed by
close code 1000, even when Stop came after the negotiated heartbeat window.
The strict peer recorded 1,664 ms detached before Stop with a 1,100 ms
heartbeat window. A retired polling SID after a server namespace disconnect
left periodic inventory running and produced no new connection.

The separate Engine.IO close packet `1` leaves the current namespace
subscribed while the transport remains usable. Both clients delivered the
next event and closed the original session on Stop. When the peer then
retired an active polling SID with HTTP 400, both clients connected again.
During the separate 2.6-second WebSocket observation, Rust reconnected after
close code 1001. The C# peer observed no second session in that interval.
The local 32-case paired wire record has SHA-256
`b666cf4c18d14fb9468fcf808263839a2f4575528826d93e2c288ff5218c62fd`.
At `f148e30` the frozen Fedora run passed all 27 scenarios, four unit
tests and Clippy. Independent readback matched all 19 source inputs to
that revision and all nine outputs to `result.json`, SHA-256
`2699d02dad8194d58504e8d810762e24f68c4f91624e492133a9bfca57d0581a`.
[Wire fixtures](../../tools/rust-qa/realtime/verify.py) ·
[Engine.IO packet definitions](https://github.com/socketio/engine.io-protocol#protocol).

### Server closes an established WebSocket

The signed .NET 3.0.4 client received WebSocket close code 1001 after its
first album event. For each of the root and `/collection` namespaces, the
peer tried three variants: a preceding Engine.IO close notice, the close
frame alone, and a close frame followed immediately by TCP shutdown.
All six cases retained a single session and event. An authenticated REST
inventory invoked by the driver succeeded 77.77–77.79 seconds after the
close. In the two controls with abrupt TCP loss and no close frame, the
signed client established a direct WebSocket session after 18–19 ms and
delivered the second album event. The signed results have SHA-256
`81c29b85269321585ca2381f25c3476681cba96d12ddb45a6c79f0aa63a62682`.
[Pinned WebSocket receive implementation](https://github.com/doghappy/socket.io-client-csharp/blob/9deebcfe8079164d269ec4f22ba58589366014fb/src/SocketIOClient/Protocol/WebSocket/WebSocketAdapter.cs#L24-L53).

Before the correction, Rust opened a second session about 0.5 seconds
after close code 1001. After the correction, the six corresponding Fedora
x64 trials kept one session through the 28-second observation. Periodic
REST inventory continued. Both abrupt-loss controls still reconnected
through polling and upgrade, then delivered the second event.

On the connection held open by the peer, the signed client deferred its
close until application shutdown. Rust sent a masked close reply as soon
as it received the peer's close frame. This follows the WebSocket closing
handshake. Both fixtures check the number of application sessions and
events separately from the transport used for a retry. The strict native
suite also checks the exact reply reason, EOF and at least three
authenticated inventory requests after the closing handshake.
[WebSocket closing handshake](https://www.rfc-editor.org/rfc/rfc6455#section-5.5.1) ·
[Native peer](../../tools/rust-qa/realtime/verify.py).

All 29 strict scenarios and five unit tests passed on Fedora x64. Both
close peers observed twelve authenticated inventory requests after EOF.
The admission-state test verified that a broken pipe while sending the
close reply preserves the established session's no-retry decision. That
decision is recorded before the bounded write begins. The frozen build
receipt has SHA-256 `8ec897639ba542c3684283e7c15e0029e82be2a0ae13540dd4b5e31369117695`.

### Opening the next session after an abrupt disconnect

At `20dfb10` the Rust client still started with polling after an upgraded
WebSocket lost its TCP connection. In the signed client, the server's
WebSocket offer updates the transport preference for that client instance.
On the next attempt the shipping client opened a WebSocket at the configured
origin without the old SID. The peer sent a new Engine.IO OPEN. It received
the masked `40` or `40/collection,` directly and delivered the second
event. Both signed trials also recovered when that first direct request
returned HTTP 503. The successful direct retry followed 12.493 seconds
later for the default namespace and 11.404 seconds later for the named one.
[Pinned transport selection](https://github.com/doghappy/socket.io-client-csharp/blob/9deebcfe8079164d269ec4f22ba58589366014fb/src/SocketIOClient/SocketIO.cs#L373-L404).

The Rust implementation now remembers that offer across connection attempts.
Its fresh direct handshake uses the original header, origin, TLS verifier
and frame limits. In the named case the peer verified a masked pong before
the OPEN and a masked namespace join immediately afterwards. A second
upgrade offered in the direct OPEN produced no extra probe. The HTTP 503
and HTTPS redirect controls both led to another direct attempt. The redirect
destination received zero requests. In the polling-only control, expiry
of the first SID led to a second polling session. All five controls
delivered two events and the correct final namespace disconnect.

The Fedora x64 frozen build passed all 33 wire scenarios and five unit
tests. The native receipt has SHA-256
`75e2a918b1dc44acf673ff299681a0f152f74c0b4b79a9a5d28c230cbf3fc278`.
[Wire assertions and original request fields](../../tools/rust-qa/realtime/verify.py).

A separate peer returned HTTP 503 on the *initial* SID-bound upgrade,
before namespace admission. In both signed trials the polling connection
closed before that response. The server saw no later SID-bound polling
GET, application event or retry during 95 seconds. Separate runs cancelled
cleanly after 42 seconds and completed two requested REST inventory reads.
On the same peer the Fedora Rust client admitted an event over polling,
then admitted a second after direct recovery from a later polling failure.
Initial upgrade admission therefore still differs. The paired comparison
has SHA-256 `ee5362d9df916405ea5690ad0976fc0fef07f9547569fc9c8c6b87ac1f507977`.

### Stopping an established session

The signed Linux x64 Flatpak 3.0.4 assemblies ran on their delivered .NET
10.0.12 runtime against a loopback peer. Each of the four connections had
delivered an album event before the driver called `StopAsync`. For ordinary
polling the peer received one final POST with `41` while a GET was pending.
The corresponding packet on the `/collection` namespace was `41/collection,`.
On WebSocket the peer received the same namespace packet, then a normal close
frame with code 1000 and the reason `io client disconnect`. It replied with
code 1000. The four C# stop calls took 9.68–12.29 ms. The shipping wire
record has SHA-256 `a074f7d59b1cd8660a1238501137d7b09ed640f8f3d84e3da68c92116c701c9e`.
[Package and assembly provenance](rw02-yaml.md#reading-the-rust-output-with-the-delivered-304-flatpak-assemblies) ·
[Shipping stop deadline](../../src/ImmichFolderWatch.Immich/ImmichRealtimeClient.cs).

On `1e3c024` the Rust process reported a normal stop while the peer observed
no final polling POST. The WebSocket ended at TCP EOF. The corrected supervisor
signals the owning session and waits up to two seconds. An acknowledged
namespace sends its disconnect on the active transport. The WebSocket then
exchanges close frames. A pending read can be interrupted, and an outstanding
write finishes before the disconnect starts.

The native Fedora x64 run passed all 18 loopback scenarios, including both
namespaces and both transports. With an 850 ms run budget, the process
exited at 855 ms when the namespace acknowledgement was withheld. The
peer saw no disconnect for that unacknowledged namespace. When an upgraded
peer withheld its close reply, the process reported a stop timeout and
exited at 2,857 ms with one connection attempt. The session receipt has
SHA-256 `8fa72e38a325c3ebd49c0f4f3a0dda0840629e23762578ec7f082cb248b2104f`.
[Native runner and wire checks](../../tools/rust-qa/realtime/README.md).

### Namespace acknowledgement during a transport upgrade

At `bcacfaf` a loopback server held the namespace polling GET until the
client probed its advertised WebSocket. The Rust client waited ten seconds
for the polling acknowledgement, timed out and received no subscribed event.
On the same peer, the signed 3.0.4 Linux x64 assemblies upgraded, accepted
the acknowledgement on WebSocket and received the event in both the default
and `/collection` namespaces.

The corrected client receives polling packets while qualifying the new
transport. After a positive probe it stops issuing GETs and drains the
current GET and its writes before sending the Engine.IO upgrade packet.
The original namespace deadline applies on either transport. In the
Fedora x64 trial the peer released a held polling GET with a heartbeat
and a noop, held the HTTP pong response for a further 150 ms, and then
observed `5` before sending the WebSocket namespace acknowledgement. A
second peer withheld the probe pong while its polling transport delivered
the acknowledgement, an album event and eight heartbeats. The client
answered all eight and shut down on the same polling session.
[Engine.IO upgrade procedure](https://socket.io/docs/v4/engine-io-protocol/#upgrade) ·
[Wire observations](../../tools/rust-qa/realtime/verify.py).

The local native suite passed 20 scenarios. In separate one-second
comparisons, both namespaces delivered an event and completed the close
exchange with the acknowledgement on either transport. The original
polling control returned a namespace acknowledgement on **every** GET.
If another GET reached it before the probe completed, Rust reported a
protocol error on the repeated CONNECT. A control that acknowledges
each namespace once passed all four combinations. The late-acknowledgement
handler was identical in both comparisons. The full native suite's
`sessions.json` has SHA-256
`769508629866d3efe0f9befdd2212bdc36f1b31a2a84a8634e14f3ef3b779ddf`.

### Four native transport results at e2f161b

The native Windows and Ubuntu x64 and ARM64 clients each passed all 20
loopback scenarios. On every host, the peer recorded six polling
disconnects and five WebSocket disconnects in their expected namespaces.
Each WebSocket disconnect was followed by close code 1000 with the reason
`io client disconnect`. Four peers replied. The fifth deliberately
withheld its reply and the client reported a timeout after one attempt.
The table gives total process times including the 850 ms fixture budget.
[Native assessment run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795).

| Host and original archive | Polling pongs during stalled probe | Stop before namespace ACK | Stop with close reply withheld |
| --- | ---: | ---: | ---: |
| [Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/15000092332) | 8 | 853 ms | 2,855 ms |
| [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/15000400813) | 8 | 853 ms | 2,854 ms |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/14999848146) | 14 | 860 ms | 2,891 ms |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45565563795/artifacts/15000601243) | 14 | 878 ms | 2,886 ms |

When the probe stalled, all four clients received one subscribed event on
their original polling session, answered every heartbeat and sent the final
polling disconnect. The early-ACK case delivered an event on either side of
the upgrade. The late-ACK case drained its pending polling pong, upgraded,
received its namespace acknowledgement on WebSocket and delivered the
event. Stopping before acknowledgement sent no disconnect packet.
[Peer assertions](../../tools/rust-qa/realtime/verify.py).

Independent readback matched the four ZIP digests to GitHub, verified all
ten output hashes per archive and reconstructed each native dependency
graph digest. All 19 source hashes per host matched the recorded revision
with its checkout line endings. Both Windows hosts used CRLF for
`rust/toolchain-inputs.json`, `audit-graph.py` and `check-toolchain.py`.
The local comparison under `artifacts/rust/hosted-realtime/45565563795/`
retains the original archives, API metadata and replay script. Its
`four-host-realtime.json` has SHA-256
`2c740c04b931d06d067fd28ba5b8c92bb5c741ca11cc22926262cb5f4171c297`.

### TLS endpoint identity

The TLS observer now distinguishes a trusted issuer from a certificate that
names the requested host. It issues two ephemeral server certificates from
one private CA, for `127.0.0.1` and `127.0.0.2`. OpenSSL verifies each chain
for its named address and rejects the second leaf for the first address.
Every Rust connection goes to the private server at `127.0.0.1`. The observer
records the TLS ClientHello independently of parsed HTTP requests and retains
the public certificate hashes. Neither the Rust client nor the OS trusts any
additional certificate after the process exits.

The native Fedora x64 entry point passed all sixteen cases offline in a
private loopback namespace. The matching leaf completed the Socket.IO
upgrade and 17 HTTP requests. The valid certificate for the other address
reached the TLS server and produced zero HTTP requests. The unrelated CA
control also reached TLS and produced zero HTTP requests. The successful and
wrong-address cases used the same CA digest. All seven build and test steps
passed, including the source check for 109 registry packages and 192 notices.
The observed wire report has SHA-256
`e2c9b69c82811e9b9f667f6a2468a49d7bd12efab35b742eb7c6aed122c21f77`.
At `8091469` the Ubuntu x64 and ARM64 archived results each contain sixteen
cases and 191 peer-observed HTTP requests. The matching certificate allowed
one WebSocket probe and upgrade and thirteen inventory reads. Both refusal
cases reached the peer's TLS listener and sent zero HTTP requests. The
redirect destination received no request or credential. The original
`sessions.json` SHA-256 values are `7c2e4b46f378eddbb4fb08eaf12cc9f62fe4363d4d633e040f179c34a0e4d17d`
and `0557e8fd8bdae9969dfadc70305d5d63b622f62fc5269e4da76b00c7751a1b05`.
The full Windows archives show the same sixteen cases and 191 HTTP requests
on each architecture. The matching leaf completed all 17 requests, including
13 inventory reads and one successful upgrade. Both rejected leaves reached
TLS and sent zero HTTP requests. Neither redirect destination received a
request or credential. Independent readback verified all nineteen source
digests, ten output digests and the resolved graph on each host. The Windows
x64 and ARM64 `sessions.json` digests are
`8dae434a716f5677c080cba9323226d25d968d8fc3f74f36cfc9e8d12ccfc76a` and
`029c825cf9b46fef8e92f017e427098048db4dbc7a676d15d19c927178810ad9`.
[Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45067343500)
· [Wire fixture](../../tools/rust-qa/realtime/verify.py)
· [Client transport policy](../../tools/rust-qa/realtime/src/transport.rs).

## Dependency and native input review

The assessment has an independent lockfile, SHA-256
`8089303faf289786169b79eb370c5afdabbff0034482ab26cf71220f3df3dcdf`.
The four normal/build target inventories cover 114 distinct registry packages,
two first-party packages and 202 supplied notice files. The lock includes another
38 registry packages outside those native target profiles. The audit records
original archive hashes, actual feature sets, build scripts, proc macros and
notices. No fonts or shaders occur in the active archives. The runner verifies
each active unpacked source tree against the original before compilation.
[Lockfile](../../tools/rust-qa/realtime/Cargo.lock) and [per-target evidence pins](../../tools/rust-qa/realtime/inputs.json).

| Input | Selected function and licensing |
| --- | --- |
| reqwest 0.13.5 | `rustls-no-provider` only. Hyper provides HTTP/1 upgrade I/O. No HTTP/2, HTTP/3, compression, cookies, OS proxy detection or native TLS feature. MIT branch. |
| rustls 0.23.46, ring 0.17.14 | `ring,std,tls12`, with TLS 1.3 available. rustls uses the MIT branch. ring includes ISC, Apache-2.0 BoringSSL/Fiat code, and the embedded once_cell dual license. Preserve file-level attribution. |
| tokio-tungstenite 0.30.0, tungstenite 0.30.0 | Handshake and frame codec. HTTP already owns the connection and certificate policy. MIT branches. SHA-1 implements the RFC 6455 challenge. |
| tokio 1.54.1, futures-util 0.3.34 | Single-thread harness runtime with I/O, timers, bounded wakeups and sink support. MIT branches. |
| serde 1.0.229, serde_json 1.0.154 | Standard allocation, derived handshake ACK structures and a bounded event visitor. MIT branches. |
| IDNA/ICU and Unicode tables | Preserve Unicode-3.0 data and software notices, including the additional terms on unicode-ident. These tables support URL handling. |
| Other selected inputs | MIT where offered, Apache-2.0 for sync_wrapper, BSD-3-Clause for subtle, ISC for rustls-webpki and untrusted, MIT for tracing-core's nested spin code. Each selected expression and notice digest is recorded in the inventory. |

The source review found permissive terms supporting this scoped assessment
under AGPL-3.0-only when notices, attribution and applicable source obligations
are retained. Re-evaluate the combined product graph and deliver its notices
and corresponding source with candidate packaging. [ring's original archive](https://static.crates.io/crates/ring/ring-0.17.14.crate),
[Unicode license](https://www.unicode.org/license.txt), [FSF license list](https://www.gnu.org/licenses/license-list.en.html)
and [AGPLv3](https://www.gnu.org/licenses/agpl-3.0.en.html).

The transport also selects base64 0.23.1. Its upstream archive contains the
CLion promotional logo identified in the [storage source review](rw02-storage-inputs.md#license-and-asset-findings).
The native network evidence contains the inventory and hashes. The combined
offline source bundle needs the verified logo exclusion and its edited README
reference before redistribution.

The ring archive contains 17 preassembled Windows COFF objects. Twelve are
selected for Windows x64. On Linux x64 all twelve were independently regenerated
from the archived Perl assembly generators with NASM 2.13.03. Their assembly
and normalized loadable object bytes matched, including relocation records,
symbols and unwind data. Only debug paths and the COFF build timestamp were
excluded. The original and normalized files have separate hashes. The archive
declares a dirty VCS snapshot at `2723abbca9e83347d82b056d5b239c6604f786df`.
The original .crate SHA-256 identifies the exact source. Linux builds assemble the
selected native sources. Windows ARM64 uses Clang for ring's C/assembly.
[Reconstruction procedure](../../tools/rust-qa/realtime/README.md#windows-x64-crypto-object-reconstruction)
and [ring build script](https://github.com/briansmith/ring/blob/2723abbca9e83347d82b056d5b239c6604f786df/build.rs).

The Windows ARM64 graph also includes Microsoft's `windows_aarch64_msvc`
0.52.6 import library `windows.0.52.0.lib`, SHA-256
`ca85dd7757f338ba00d0bc19229f176ee426a707425ee4fcf205ec491a95bd5a`.
Ring's ARM detector calls `kernel32!IsProcessorFeaturePresent`. The crate's
Apache/MIT notices and upstream metadata revision
`db06b51c2ebb743efb544d40e3064efa49f28d38` identify this platform input.
Reconstruction from Microsoft's three WinMD files matched all 20,551 ARM64
imports across 371 modules. The original and LLVM-built library linked the
actual `windows-sys` binding into byte-identical ARM64 DLLs. The native
MSVC build, full transport relink and four-target product packaging have
separate gates. [Reconstruction, sources and local comparisons](rw02-windows-imports.md).
The Linux x64 test executable dynamically linked
glibc and libgcc_s with the system ELF loader. [Metadata reader](https://github.com/microsoft/windows-rs/blob/db06b51c2ebb743efb544d40e3064efa49f28d38/crates/tools/lib/src/lib.rs)
and [MSVC generator](https://github.com/microsoft/windows-rs/blob/db06b51c2ebb743efb544d40e3064efa49f28d38/crates/tools/msvc/src/main.rs).

## Runtime observations

The 2026-11-20 Linux x64 release build ran in a network namespace with only
loopback, an empty home, a read-only source/cache and temporary test keys.
Native rustc 1.100.0, rustfmt, Clippy with warnings denied, three Rust regression
tests and all 15 independent wire scenarios passed. The native graph had 111
nodes, including 109 reviewed registry archives, 4,992 verified unpacked files
and 192 supplied notice files. [Repeatable native command](../../tools/rust-qa/realtime/README.md)
and [independent wire fixtures](../../tools/rust-qa/realtime/verify.py).

| Wire observation | Exercised result |
| --- | --- |
| Polling and namespaces | Server observed the expected OPEN request and namespace CONNECT. Nine subscribed events arrived. Unrelated names and a foreign namespace produced no event wakeup. |
| WebSocket | Server observed `2probe`, `5`, masked client frames, RFC 6455 pong and Engine.IO pong. A fragmented JSON event with a Socket.IO acknowledgement ID requested refresh. |
| HTTPS/WSS | The trusted fixture completed polling and WebSocket upgrade. A different CA yielded no HTTP request or credential. Plain HTTP without explicit opt-in was rejected before a request. |
| Redirect and downgrade | Both the initial polling redirect and the HTTPS-to-HTTP WebSocket-upgrade redirect produced zero requests and zero credentials at the other origin. Polling continued after upgrade refusal or a refused probe. |
| Bounds | An exact 4 MiB polling event arrived. A declared over-limit HTTP body, a chunked over-limit body, and two individually permitted WebSocket fragments totalling 4 MiB + 1 each failed before any event wakeup. |
| Lifecycle | A disconnect produced a second successful authenticated namespace session. A missing heartbeat expired. Cancellation interrupted a pending long poll and a 30-second reconnect delay. Periodic authenticated inventory reads continued after transport failure. |

Each native run writes complete source and output hashes in `result.json`, the
selected dependency/feature inventory in `graph.json`, and client/peer observations
in `sessions.json`. The corresponding cross-target inventories contained 111
nodes on Linux ARM64 and Windows x64, and 114 on Windows ARM64. Native observations
from those hosts belong in the overall acceptance record. The fixture covers
the nine subscribed text events. Product inventory reconciliation, alternate
protocol versions, use of OS trust and full synchronization parity require
their later integration checks. [Acceptance record](acceptance.md).

The local run is retained under
`artifacts/rust/realtime-assessment/source-bound-linux-x64/`. The isolated mount
excluded Git metadata. Its `result.json` binds the observed first-party and QA
source bytes individually. On this run the pending-poll case stopped at 853 ms
for its 850 ms budget, and the reconnect case completed two upgrades and two
heartbeats. The tracked build recipe reproduces the independent object check.

| Local evidence | SHA-256 |
| --- | --- |
| Native `result.json` | `53e710e4f1d7ba7195a5344e9f3c9b84b6ff6bda79937e4cb3235314c656f3c0` |
| Wire `sessions.json` | `646d2c0066198d3f9795de5706e279ec1d5d78d0c219966480a267488721da82` |
| Target `graph.json` | `0f919353bd2e352050ea4b97cc830a08a06ac4200c051816e9cb4aa2977f615a` |
| Release probe | `912d867e20196e7ad83e3785b726d3d90bcbe9c962a808f42213d7d64f7ebdd5` |
| `artifacts/rust/realtime-assessment/build/rebuilt-objects.json` | `ce738b8f3ebac873c36e00243bc9e202c39e314c5c8e5d1cefd92c18a7ad44c9` |
