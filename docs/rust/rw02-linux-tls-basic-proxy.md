# Linux HTTPS through an authenticated HTTP proxy

The Linux transport handles a named HTTP proxy from the environment when the
Immich origin uses HTTPS. It first asks for a CONNECT tunnel anonymously.
If the configured proxy returns 407 and offers a supported Digest or Basic
challenge, the client may repeat the same operation once using that proxy's credentials. The ordinary rustls
connection inside the accepted tunnel validates the Immich origin before
sending an API key. The HTTPS, redirect and timeout settings are identical
for both clients. The retry uses the remaining request budget and disables
idle connection reuse on its authenticated client. TLS, cancellation and
a later error from the origin cannot select that client. A matching
`NO_PROXY` entry takes the direct route.

## Measurements against 3.0.4

On Fedora 45 x64, the development driver called the signed Linux 3.0.4
ImmichAssetClient and ImmichRealtimeClient assemblies. The fixed sender,
listener, test CA and synthetic key were confined to a fresh loopback
namespace. The subjects used a named namespace and the ordinary HTTPS REST,
polling and WSS paths. The password included percent-escaped characters.
Both TLS peers required a matching host name and private issuer. The
observer matched each inner request to its connection and recorded only
whether the supplied proxy credential was absent, correct or incorrect, or
used another scheme.

| Route / relay response | Signed client | Original Rust connector with loopback admission enabled |
| --- | --- | --- |
| Anonymous | Four anonymous tunnels, one event, close 1000 | Nine anonymous tunnels, one event, close 1000 |
| Basic, correct password | Four initial 407s followed by four authenticated tunnels | Nine tunnels included Basic on the first CONNECT |
| Basic, incorrect password | Authentication failed before TLS | First CONNECTs carried the incorrect credential. No TLS handshake |
| Digest only | .NET started anonymously, then answered using Digest. The fixed relay rejected that method | The relay received the Basic credential before offering any method |
| Bypass with a credential-bearing proxy environment variable | Direct TLS, no proxy connection | Direct TLS, no proxy connection |

The first Rust attempt with the previously archived ELF stopped at the
fixture's credential-free endpoint comparison. A second run admitted only
the fixed loopback relay and measured the unmodified reqwest connector.
Its report is `artifacts/rust/realtime-assessment/linux-tls-basic-admitted-01/report.json`,
SHA-256 `120d736f147c84fcaee3678407d89937c3727466bef32c0bc2982719595bf831`.
The [detached reader](../../tools/rust-qa/realtime/replay_linux_tls_basic_proxy.py)
accepts this baseline with `--baseline`. The corrected comparator uses its
default mode. The Linux candidate supports the scoped Basic challenge.
Digest authentication remains a distinct shipping behavior.

## CONNECT error metadata

The upstream connector retained the status of a refused CONNECT but discarded
its authentication challenge fields before the first-party transport could
inspect them. The private source changes two Rust files. A 407 carrying
challenge fields exposes them through a typed source on the same connection
error. The existing status description, TLS verification, retry choice and
actual connector stay independent of the new metadata. Challenge values are
marked sensitive. The first-party adapter checks the scheme, including quoted
commas in a different scheme's parameters. It never derives permission to
send a password from a formatted error message.
[Original tunnel source](https://github.com/hyperium/hyper-util/blob/23a868965964c1d6bb1b94f30ba4c420a4bebe7c/src/client/legacy/connect/proxy/tunnel.rs) ·
[Maintained diff](../../tools/rust-qa/realtime/hyper-util-connect.patch).

The exact hyper-util 0.1.21 archive has SHA-256
`ddc03d96684f9226b8a787cdb71488417b53ab5ea8fdb1dac946cb9431cc8bff`.
It identifies upstream commit `23a868965964c1d6bb1b94f30ba4c420a4bebe7c`.
Its original Sean McArthur MIT license has SHA-256
`9e0a97848ea543aef745c98e84fde696a9a3e0735538f6daefdd3cb1942effc1`.
The patch SHA-256 is `761b075d5fbf1d5c98c478bcc6f443898a1171973d4dcc557380ce45d84f9cd0`.
Reconstruction compares all 62 compiler inputs to the original archive or
the two reviewed replacements. The resulting file map has SHA-256
`acd12c39160b6bfe7d7872fcbb6b7974ae880b23e01936576934c23127f4d4a4`.
The native run retains the archive, diff and original license with the
compiler results. Two independent reconstructions agreed. Verification
rejected modified versions of either Rust file, a changed notice and an
unexpected extra file. After accounting for the source and lockfile receipt,
all four target graphs matched their previous package and feature records.
[Original crate](https://static.crates.io/crates/hyper-util/hyper-util-0.1.21.crate) ·
[Original license](https://github.com/hyperium/hyper-util/blob/23a868965964c1d6bb1b94f30ba4c420a4bebe7c/LICENSE) ·
[Reconstruction](../../tools/rust-qa/realtime/hyper_util_source.py).

## Native entry points

Both Ubuntu architectures use the [normal Linux transport suite](../../tools/rust-qa/realtime/README.md).
Eight HTTPS cases exercise valid and invalid credentials, a non-Basic
challenge, a change to a different scheme after a successful realtime event,
direct bypass, a mismatched TLS identity, a 407 generated inside an
established HTTPS connection by the origin, and a redirect to a second
listener. The distinct signed Linux comparison uses the existing private
assembly and peer archive. Run the latter from the repository root with a
new output filename and supply the native release binary's measured digest.

```sh
python3 -B tools/rust-qa/realtime/linux_basic_proxy.py --tls \
  --archive artifacts/rust/realtime-assessment/proxy-fedora-05 \
  --sdk artifacts/flatpak-local-2.11.2/sdk \
  --candidate artifacts/rust/realtime-assessment/linux-tls-basic-final-01/ifw-realtime-probe \
  --candidate-sha256 a896365075ed49ae7f08df6bde14fe6ec8a39ab9d29c66bd7eca9c158ddf5a04 \
  --output artifacts/rust/realtime-assessment/linux-tls-basic-repeat.json
python3 -B tools/rust-qa/realtime/replay_linux_tls_basic_proxy.py \
  artifacts/rust/realtime-assessment/linux-tls-basic-repeat.json
```

The final Fedora x64 paired report at
`artifacts/rust/realtime-assessment/linux-tls-basic-final-01/report.json`
has SHA-256 `82fdfa779bccce32c6c794d71488f0ce1f88717b27df62c321170e8596c9dc4b`.
The new Rust ELF received nine Basic challenges on nine anonymous CONNECTs
and established nine authenticated tunnels. All requests inside these TLS
connections carried the application key and no proxy header. The WebSocket
delivered one event and closed normally. The incorrect password caused six
407 pairs before any TLS request. A Digest-only relay received six anonymous
CONNECTs and zero Basic credentials. A direct bypass made zero connections
to that relay. The detached reader checked all ten signed and native cases.

The full native Fedora x64 assessment ran the same ELF and passed **62
wire scenarios and 17 unit tests**. Its final receipt at
`artifacts/rust/realtime-assessment/linux-basic-proxy-native-tls-01/result.json`
has SHA-256 `6a1d49fc9f4e87e6f36fb1cb0b1de8b833c10d236bf9a249cc2e8f35d5be9ee1`.
The original wire observations in its `sessions.json` have SHA-256
`94abc63a552f378bfc629cb61903357fde35f8a9d2e40b4d2392e81520a6009e`.
Independent readback matched all 32 source files and twelve outputs,
including the upstream crate, its MIT license, the patch and the same
program digest used in the ten-case signed comparison. The graph contained
108 unmodified registry inputs and one reconstructed crate, 4,992 verified
files and 192 notices. Rustfmt, first-party warnings-denied Clippy and
the offline release build passed. The compiler also reported an unused
`timer` parameter in the unmodified hyper-util `client.rs`.
This result covers Fedora x64. The Ubuntu x64 and ARM64 runners select
the same Linux cases. Full Digest support and installed product networking
remain open.

## Native hosted transport at bbd1b73

Ubuntu x64 and ARM64 each passed 62 wire cases and 17 unit tests. In the
successful Basic case each proxy observed 13 anonymous challenges and
13 authenticated CONNECTs. Both clients delivered the event and closed
the WebSocket with code 1000. On both architectures the bypass used a
direct connection, and an origin 407 inside a successful tunnel sent
no credentials to the proxy. Windows ARM64 passed its 49 wire cases and
18 unit tests. Detached readback checked every indexed output and all
32 source files in each original ZIP.

| Native archive | Actions SHA-256 |
| --- | --- |
| [Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46100147946/artifacts/15244848026) | `2342c37a29b62322cac4e6f2390e3787d357d4b0e99d6c74fa81ff3722a854e1` |
| [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46100147946/artifacts/15245410870) | `f8964a2dc492d6952bb4591fa70c0f5fe06cc99b70d2d64eb84283b3173cd665` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46100147946/artifacts/15245650046) | `ecc088fd019f55215e9dd4193004d9e2739d3ff0fdbc0b5bf2594f31c42d464b` |

## CONNECT Digest in the shipping Linux client

The signed 3.0.4 client responded to both SHA-256 and MD5 challenges
with `qop=auth`. The request line named the fixed loopback host and port,
but the Digest `uri` field contained `/`. A relay checking the authority
rejected the response even with the correct synthetic password. A second
relay accepted the historical URI only on that same fixed route. It
verified the response hash before establishing TLS. For each algorithm the
client then made four authenticated tunnels, read the REST inventory,
received one event and closed normally. An incorrect password established
zero tunnels on either relay. The Rust Basic-only binary sent anonymous
CONNECTs and received 407 in every Digest trial. That binary predates the Digest implementation below. [Proxy Digest protocol](https://www.rfc-editor.org/rfc/rfc7616#section-3.8).

Add `--digest` to the Fedora comparison command above, using a fresh
output path. Replay the captured responses with
`replay_linux_tls_basic_proxy.py --digest-reference <report.json>`.
The sixteen original cases are in
`artifacts/rust/realtime-assessment/linux-tls-digest-reference-02.json`,
SHA-256 `d3ef4d1f0baf52bce96427095e70f7a35af1280e90f9d80231e511165515fafe`.
The receipt records route, credential outcome and URI form. Passwords
and challenge responses stay inside the disposable network namespace.


## Authority-bound Digest on Fedora x64

The Linux client selects a supported Digest challenge from the selected HTTP
proxy's CONNECT response. It binds the digest to the authority actually used
on the request line. In the sixteen-case signed comparison, the Rust client
established nine TLS tunnels in each of the four positive cases. Both strict
and legacy-compatible relays accepted its authority with SHA-256 and MD5.
The peer observed an inventory, polling, a WebSocket event and a normal close
inside TLS. All four wrong-password trials stopped before TLS. The signed
client kept its historical root URI and passed on the two compatible relays.

The release executable's SHA-256 is
`d32aee73a5e4747655cdc92f34f9c1c47c2007ebeeaf0dcbcc1dfb3af17493b1`.
The original sixteen-case receipt is
`artifacts/rust/realtime-assessment/linux-tls-digest-final-01.json`,
SHA-256 `7e7eb7eab5fd7057e51c0f2695ca89a7b4c66f299ad1a0fd900618535a63ba4a`.
Replay it with `replay_linux_tls_basic_proxy.py --digest <report.json>`.
For the ten earlier scenarios with a Digest-capable binary, use
`--basic-with-digest`. The ordinary Linux suite also verifies the two
algorithms with both correct and incorrect credentials. These observations cover qop `auth`. The fixed-nonce comparison below adds
count validation. Plaintext Digest remains a separate case.

The Linux transport selects the MIT license for RustCrypto `md-5` 0.11.0 and
`sha2` 0.11.1. The exact MD5 archive matches crates.io and source revision
`b5051e5a5e7dc86a6c27c1ec7a390744ebcfb97a`. On the two Linux targets
the MD5 compression function uses safe Rust; this package adds no build
script or native object. The target inventories retain both original license
files for both packages. All previously selected target packages and features
are identical to the previous inventories. The two Windows package sets are
identical as well. [Reviewed hashes and original notices](../../tools/rust-qa/realtime/inputs.json) ·
[RustCrypto MD5 sources](https://github.com/RustCrypto/hashes/tree/b5051e5a5e7dc86a6c27c1ec7a390744ebcfb97a/md5).

### Native Ubuntu and Windows receipts at ed9268e

On Ubuntu x64 and ARM64, each native process passed 66 wire scenarios and
19 unit tests. Each of the two Digest algorithms completed thirteen
authenticated tunnels after thirteen anonymous challenges. The peer
received a normal WebSocket close. Each wrong-password control stopped
ten credentialed attempts before origin TLS. On Windows ARM64, all 49
wire scenarios and 18 unit tests for that target passed. Detached
readback matched every indexed output and 35 source files per archive.
[Native transport run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46102630472).

### Multiple requests with the same proxy nonce

A Fedora relay that checks nonce counts accepted the earlier executable's
first correct request and declined all six subsequent attempts with the same
count. None of its four positive Digest cases reached a realtime event.
The revised transport keeps the count and random client nonce together
for each of the last 32 server nonces on the configured proxy. Concurrent
requests reserve distinct counts. Eight parallel calls in the native unit
test used 1 through 8. A different nonce started at 1, followed by 9 for
the original nonce. The table retains only fixed-size hashes and counters.
A failure to generate or reserve a Digest response stops the request.
[Digest nonce-count definition](https://www.rfc-editor.org/rfc/rfc7616#section-3.4).

In each of the four successful comparisons at the loopback relay, the
corrected Rust executable used counts 1 through 9. Both credentials
and the requested authority were verified before TLS. All four negative
cases produced zero authenticated requests. The signed .NET control ran
with its historical relay behavior. The binary SHA-256 is
`460febc0520dce4595186e93533dbfaef527dcf515b77b09c0a98fcf183f609b`.
Twenty unit tests and all 66 wire cases passed on Fedora x64. Replay the
sixteen paired cases with `--digest-counts`. The baseline and corrected
reports are in `artifacts/rust/realtime-assessment/` as
`linux-tls-digest-count-baseline-01.json` (SHA-256
`a9b57ffbe2ac7cdd6a92a37a219af13cc9fa761630155845ec3cbd255891ffe5`)
and `linux-tls-digest-count-final-01.json` (SHA-256
`e6d6a45d5aa61557d50d1e29efe3051ccbd1066c0619c61af1b9c039fc7fdf79`).

### Native nonce counts on Ubuntu x64 and ARM64 at a2e54f5

On both Ubuntu architectures, the relay accepted nonce counts 1 through 13
in order for MD5 and for SHA-256. Each accepted CONNECT followed an
unauthenticated 407 challenge. All thirteen tunnels completed TLS and carried
authenticated origin requests. The peer observed the subscription event,
namespace disconnect and normal WebSocket close. With an incorrect password,
each relay rejected ten credentialed retries, accepted zero counts and observed
zero TLS handshakes. The parallel-count and rotated-nonce unit test also passed
on both architectures. [Native transport run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/46103806187).

| Native host | Unit tests | Wire scenarios | Original Actions ZIP SHA-256 |
| --- | ---: | ---: | --- |
| Ubuntu x64 | 20 | 66 | `1ff8ae45dc4b8767d3214733f39049246481c1146085000c31d4a984d2057686` |
| Ubuntu ARM64 | 20 | 66 | `09239e8835d8e40de2a2a609d49de3d647cbf8741b61036407338161f2485231` |
| Windows 11 ARM64 | 18 | 49 | `dc279452b4d733247090035c0ae5dc73ee607d88ba51a1a34dbf7eefe18c362f` |

The Windows ARM64 control recorded 13 authenticated HTTPS requests through
two TLS tunnels. The HTTP bypass case connected directly and received its
event. The archived executable's PE machine field identifies ARM64. Its
target graph excludes the Linux-only MD5 dependency.

The detached replay matched the three original ZIPs to the Actions digests,
verified every indexed output and compared 35 source files per archive with
commit `a2e54f5`, accounting for Windows checkout line endings.
The archives, Actions metadata and replay are in
`artifacts/rust/realtime-assessment/hosted-a2e54f5/`. Running
`python3 -B artifacts/rust/realtime-assessment/hosted-a2e54f5/replay.py`
reproduces `verified.json`, SHA-256
`b14d6458fb9165695994621bf6658e8e1c8fbbfbbd768cb69b4440071ce5c169`.
