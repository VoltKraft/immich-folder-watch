# Native realtime assessment

This standalone RW-02 workspace exercises a Rust Engine.IO v4 and Socket.IO v5 client
over real loopback connections. The client imports the application's bounded framing
crate. Python supplies synthetic peers and receives the observations. The assessment
build has no profile loader, file operations or production Immich endpoint.

Run on each native host from the repository root with the pinned Rust 1.100.0
compiler, Cargo, rustfmt and Clippy on PATH. Use Python 3.11 or newer and a
native C compiler/linker. Windows uses a Visual Studio development environment.
The ring build also requires Clang on Windows ARM64. The OpenSSL CLI generates
the temporary synthetic CA and server certificate. On Windows, the driver also
recognizes the standard Git for Windows installation of OpenSSL.

```text
python tools/rust-qa/realtime/run.py x86_64-unknown-linux-gnu --output artifacts/rust/realtime-native/x86_64-unknown-linux-gnu
```

Replace the target with `aarch64-unknown-linux-gnu`, `x86_64-pc-windows-msvc` or
`aarch64-pc-windows-msvc` on its native machine. Use an empty output directory.
The runner uses `artifacts/rust/realtime-cargo` by default. Supply `--cargo-home DIR`
to select another isolated cache and `--offline` after fetching the locked archives.
The native runner verifies the active compiler/host, locked target graph, archive
and unpacked source bytes, notice evidence, formatting, unit tests, Clippy, release
build and all 34 wire scenarios. Two strict polling peers accept only the
Socket.IO namespace derived by the shipping client from an escaped API URL.
They check CONNECT, the authenticated album request and DISCONNECT for the
root and a named namespace. [Signed reference and expected packets](../../../docs/rust/rw02-realtime-transport.md#escaped-api-paths-and-socketio-namespaces).

After abrupt loss of an upgraded connection the peer expects the next
request to open a WebSocket without the old SID. It sends a fresh
Engine.IO OPEN and verifies the masked namespace join and second event.
The named case checks a WebSocket ping before the OPEN. On a refused or
redirected direct reconnect, the peer checks the transport of the next
request. A polling-only control retires the first SID and observes a
second polling session. The HTTPS redirect case uses the isolated test CA.
Another named reconnect keeps both original OPEN packets and omits
`maxPayload` in each, matching the shipping client's accepted input.

The upgrade trials exercise the namespace
acknowledgement on either transport. The polling case delivers an event
before cutover. In the other case the peer releases a held poll after the
WebSocket probe and checks the polling heartbeat reply before sending the
namespace acknowledgement on WebSocket. A stalled upgrade probe checks that
polling continues to receive the namespace acknowledgement, events and
heartbeats. The peer records the namespace disconnect
for an established polling or WebSocket session. On WebSocket it also checks
the normal close code, the reason and completion of the reply. Two stop controls
withhold the namespace acknowledgement or the WebSocket close reply.
Two further peers send close code 1001 once the root or named namespace
has delivered an event. They check the masked close reply, end of the TCP
stream and subsequent authenticated inventory requests.
The TLS controls use a fresh private CA,
one server certificate for the loopback endpoint and one for a different
loopback address. The latter must complete no HTTP requests. The peer records
the incoming TLS ClientHello separately from HTTP requests. The test uses
only synthetic credentials and its own temporary trust files.

`result.json` records each step, source and artifact hashes. `graph.json` contains
the full selected feature graph, original inputs and notices. `sessions.json`
records per-scenario HTTP and Socket.IO observations and elapsed process lifetimes.
The runner fails on a changed reviewed graph or unexpected source files. The
compact, sorted-key JSON encoding of each target inventory is pinned in
`inputs.json`. A dependency change requires a fresh source and license review.

## Windows x64 crypto object reconstruction

The ring package includes NASM input, generator scripts and the preassembled COFF
objects used on this target. For independent offline verification, use Perl,
GNU objcopy with PE support, Python 3.12 or newer and NASM 2.13.03. Its published
source archive SHA-256 is `812ecfb0dcbc5bd409aaa8f61c7de94c5b8752a7b00c632883d15b2ed6452573`.
The build-only tool uses BSD-2-Clause. The exact archive and license checksums
are available in [Buildroot's distribution record](https://github.com/buildroot/buildroot/blob/2018.05/package/nasm/nasm.hash).

The verified Linux reconstruction built NASM from an extracted source directory
using the following commands in an isolated environment with GCC and GNU make.

```sh
./configure CFLAGS="-O2 -std=gnu11"
make -j4 nasm CFLAGS="-O2 -std=gnu11 -fwrapv -fno-common"
```

Run the comparison with the NASM executable, original locked crate and evidence
directory of this assessment.

```sh
python tools/rust-qa/realtime/rebuild-ring.py \
  --archive /path/to/ring-0.17.14.crate --nasm /path/to/nasm \
  --output artifacts/rust/realtime-native/ring-x64.json
```

The script compares the generated assembly and all link-relevant bytes, including
executable and unwind sections, relocations and linker symbols. It strips debug
sections containing build paths and normalizes the COFF header timestamp. The
result records separate original-object, assembly and normalized-object hashes.

See the [transport assessment](../../../docs/rust/rw02-realtime-transport.md)
for the native observations, dependency disposition and remaining scope.
