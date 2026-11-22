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
have ten-second ceilings. Shutdown drops an in-flight read, connection attempt
or reconnect delay. Delays grow to a maximum of 30 seconds. [Session](../../tools/rust-qa/realtime/src/session.rs),
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
Both Windows workflow steps also passed. Their complete desktop archives
are needed to inspect the individual observations. [Native assessment](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45067343500)
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
