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
build and 35 shared wire scenarios. Each platform also runs five HTTPS
and five explicitly enabled HTTP proxy cases. Windows adds two HTTP routing
cases and two system-provider selection controls. Linux adds four platform
trust cases. Two strict polling peers accept only the
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

After the namespace join on the opening polling transport, an upgrading client
pauses polling. The peer queues the namespace acknowledgement and events until
the client completes the WebSocket probe and sends the upgrade packet. The
refusal cases return an HTTP redirect, HTTP 503 or a WebSocket close before
admission. They check that the client starts no SID-bound poll or new session,
delivers no event and continues authenticated REST inventory requests. A stalled
probe checks inventory progress and timely cancellation, and a polling-only
control exercises cancellation of an outstanding GET.
The peer records the namespace disconnect
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

The four Linux repeats exercise the default platform verifier used by
the adapter when no application root is supplied. Each child has its own
temporary home, `SSL_CERT_FILE` and `SSL_CERT_DIR`. Two positive controls
trust the issuer only in the bundle or only in the hashed directory.
Both must complete an authenticated REST read and a WebSocket subscription.
An unrelated issuer and a wrong endpoint
name must stop at the TLS handshake. The private bundle and directory
are removed with the rest of the fixture.

The HTTPS proxy cases run the ordinary REST, polling and WebSocket
requests against a fixed loopback origin. A second listener accepts CONNECT
only for that authority and serves the test TLS endpoint on the accepted
socket. It rejects credential headers on CONNECT and records whether the
inner client completed the TLS handshake. Both paths check the synthetic
API header at the origin.
The child receives case-specific proxy settings and the fixture's expected
numeric proxy address. The suite exercises proxy use, the `NO_PROXY`
exception, precedence of `https_proxy`, and rejection of a foreign CA and
an incorrect endpoint identity.
[Shipping client and Rust observations](../../../docs/rust/rw02-realtime-transport.md#linux-proxy-selection-for-rest-and-realtime).

When plaintext HTTP is explicitly enabled, the fixture sends REST and
polling requests to the selected HTTP proxy in absolute form. To open a
WebSocket it first sends CONNECT for the configured origin, then sends the
authenticated upgrade in origin form through that tunnel. The adapter resolves the
proxy hostname when it opens the socket. A native unit test connects to a
loopback listener by name and verifies its CONNECT request. The observer checks
the request lines, synthetic API header placement, bypass, rejection of
redirects at either handshake, and a second WebSocket connection after a
dropped session. On the reconnect the peer sends the first WebSocket frame
with the upgrade response and observes its pong.

On Windows the probe reads the process environment through Win32's
case-insensitive names. A protocol-specific variable takes precedence over
`ALL_PROXY`. In a CGI environment the HTTP group uses `ALL_PROXY` when
available. `NO_PROXY` applies to both groups. A usable proxy for just one
group selects the environment provider for both, giving the other group a
direct route. The native HTTP cases exercise that direct route and the CGI
fallback. The native HTTPS priority case supplies mixed-case names and a
competing listener. If every proxy value is absent or unusable, .NET selects
the Windows system provider. The environment-only fixture reports this
boundary and avoids consulting the desktop's proxy or PAC settings.
[.NET 10 Windows environment selection](https://github.com/dotnet/runtime/blob/v10.0.12/src/libraries/System.Net.Http/src/System/Net/Http/SocketsHttpHandler/HttpEnvironmentProxy.Windows.cs)
and [system provider selection](https://github.com/dotnet/runtime/blob/v10.0.12/src/libraries/System.Net.Http/src/System/Net/Http/SocketsHttpHandler/SystemProxyInfo.Windows.cs).

`result.json` records each step, source and artifact hashes. `graph.json` contains
the full selected feature graph, original inputs and notices. `sessions.json`
records per-scenario HTTP and Socket.IO observations and elapsed process lifetimes.
The Windows result directory includes the exact executable run against the peers.
The runner fails on a changed reviewed graph or unexpected source files. The
compact, sorted-key JSON encoding of each target inventory is pinned in
`inputs.json`. A dependency change requires a fresh source and license review.

### Windows x64 on the local test guest

On a Windows x64 compiler host, append `--build-only` to the `run.py` command.
Cargo compiles the release probe and the Rust unit executable. The result
directory contains both binaries, their SHA256 values, the compiler checks
and the hashes of the source inputs. Preserve this directory as the build artifact.

On the local Windows x64 guest, use a native x64 Python 3.11 or later,
OpenSSL on PATH, the complete Actions artifact ZIP and a source export from
the recorded commit. Supply the full commit and the independently retrieved
Actions artifact digest. Run the guest command from the checkout.

```powershell
python tools/rust-qa/realtime/guest.py --archive $BuildZip --archive-sha256 $ActionsDigest --head $Commit --source-root $Source --output $Result
```

The guest verifies the archive, source and binary hashes before starting the
unit executable and the loopback suite. Its separate receipt records the
OS, Python, compiler artifact, unit output and wire observations. An older
full-run archive that retained only the release probe permits a guest wire
replay. The receipt identifies that archive's missing unit executable.

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
