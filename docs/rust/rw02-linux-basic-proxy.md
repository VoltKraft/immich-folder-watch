# Linux Basic proxy comparison

On Fedora 45 x64, the signed Linux 3.0.4 assemblies retried four requests
after an HTTP proxy issued a Basic challenge. The target used explicitly
enabled plaintext HTTP and a named Socket.IO namespace. Each client ran
alone in a network namespace containing only loopback. The fixed HTTP
proxy served the agreed origin on its own socket after CONNECT. Each trial
used fresh, randomly generated fixture credentials. The observer retained
only whether a credential matched.

| Client and proxy | Inventory | Polling | WebSocket |
| --- | --- | --- | --- |
| Signed 3.0.4, anonymous control | Read once | Opened and joined | One event and close 1000 |
| Signed 3.0.4, correct credentials | First GET received 407, authenticated retry succeeded | First GET and POST each received 407, then succeeded | First CONNECT received 407, authenticated retry succeeded. The inner Upgrade carried only the application key. One event and close 1000 |
| Signed 3.0.4, incorrect credentials | Both GET attempts received 407 | Both initial GET attempts received 407 | No upgrade or event |
| Archived Rust, anonymous control | Six reads | Opened and joined | One event and close 1000 |
| Archived Rust, correct credentials | No requests | No requests | The test entry point rejected the proxy URL before constructing a transport |

The proxy saw no application key on any CONNECT. The original Rust entry
point required exact equality with a credential-free fixture endpoint.
Its separate plaintext WebSocket adapter also rejected all proxy URLs
containing user information. Only the first rejection was reached in the
archived Rust process. [Harness](../../tools/rust-qa/realtime/src/main.rs) ·
[Adapter](../../tools/rust-qa/realtime/src/plaintext_proxy.rs).

The original report is
`artifacts/rust/realtime-assessment/linux-basic-proxy-observations-01.json`,
SHA-256 `b6dc2e010dd3a2b4d87b5e0f7563a9898e8c5d3d8c473e2e7762a0d8cff6cbaa`.
It binds the signed Flatpak commit, native Rust executable, driver source
and assembly, runtime inputs and peer sources to the previous paired archive.
The external development driver called the shipping ImmichAssetClient and
ImmichRealtimeClient directly. A separate readback checked all five outcomes.
[Paired baseline](rw02-realtime-transport.md#opted-in-plaintext-websocket-through-a-linux-http-proxy).

To repeat from the repository root with the retained local inputs, choose a
new output filename. The runner refuses other binaries or peers and launches
the processes sequentially.

```sh
python3 -B tools/rust-qa/realtime/linux_basic_proxy.py \
  --archive artifacts/rust/realtime-assessment/proxy-fedora-05 \
  --sdk artifacts/flatpak-local-2.11.2/sdk \
  --output artifacts/rust/realtime-assessment/linux-basic-proxy-repeat.json
python3 -B tools/rust-qa/realtime/replay_linux_basic_proxy.py \
  artifacts/rust/realtime-assessment/linux-basic-proxy-repeat.json
```

## First-party Linux transport

When an explicitly selected HTTP proxy URL contains credentials and the origin
uses opted-in plaintext HTTP, the adapter issues the request without proxy
credentials. A 407 offering Basic permits one retry of the same request.
The Socket.IO WebSocket opens a fresh connection to the selected proxy for
the challenged CONNECT. The inner upgrade excludes the proxy header. The
request builder disables redirects. Existing pinned reqwest code decodes
the URL user information, including escaped characters, and marks the derived
header sensitive. This trial covers plaintext HTTP to an HTTP proxy. Basic
authentication for HTTPS tunnels, Windows, other proxy authentication schemes
and installed application integration each need separate observations.

On Fedora x64 the final release ELF
`aba1c6c8144014c12e1e767db0028cef7e36f6c23f219551627729ee6da35079`
and the signed client each decoded an escaped synthetic password. Each first
sent anonymous REST, polling and CONNECT requests and retried after the fixed
proxy returned 407. The Rust process made six successful inventory reads
and delivered one event before closing with code 1000. The incorrect-password
trial produced zero successful reads and no event. With a refusal only at
CONNECT, polling joined and inventory continued but no WebSocket opened.
A Digest challenge containing the text “Basic” inside its quoted realm
received zero credential headers. No CONNECT included the Immich API key.

The paired report at
`artifacts/rust/realtime-assessment/linux-basic-proxy-comparison-02/report.json`
has SHA-256 `3901e895d117a17636f8426b73322597e1f94815c89204e9c7039fec20458281`.
Repeat the separate comparison by adding the following arguments to
`linux_basic_proxy.py` and replaying the output with the same readback.

```text
--candidate artifacts/rust/realtime-assessment/linux-basic-proxy-comparison-02/ifw-realtime-probe
--candidate-sha256 aba1c6c8144014c12e1e767db0028cef7e36f6c23f219551627729ee6da35079
```

The standard native Linux transport run on Fedora x64 passed 54 wire
scenarios, 17 unit tests, rustfmt, warnings-denied Clippy and the locked
release build. Both native Ubuntu architectures use the same entry point.
The five new cases cover Basic success, refusal at all requests, refusal
only at CONNECT, a foreign challenge and a direct route through
`NO_PROXY`. The direct origin received its synthetic application key and
no proxy header. The native receipt at
`artifacts/rust/realtime-assessment/linux-basic-proxy-native-05/result.json`
has SHA-256 `d4ff505e74925f334fd19ac1d5222af2c46f95fa04fef5407d705061ce361efa`.
Its 27 source digests and nine outputs matched independently. The existing
graph retained 109 registry inputs and 192 original notices.

## Digest for explicitly enabled HTTP origins

On Fedora x64 the signed 3.0.4 assemblies received one challenge before
retrying each album GET, polling GET/POST and WebSocket CONNECT. For the
forwarded HTTP requests they signed the path and query. For CONNECT they
signed `/`. A relay accepting those historical forms delivered the event
and the normal close with SHA-256 and MD5. A relay requiring the target
from the request line rejected both initial authenticated operations. The
previous Rust ELF answered none of the Digest challenges under either
policy. [Digest request target](https://www.rfc-editor.org/rfc/rfc7616#section-3.4.6) ·
[HTTP proxy request forms](https://www.rfc-editor.org/rfc/rfc9112#section-3.2.2).

At `1b84ad8` the Rust adapter signs the absolute URI for GET and POST,
and the destination authority including its port for CONNECT. It shares
the proxy nonce counter between those operations. In the paired trial
both relay policies accepted counts 1 through 9, with a confirmed album
read, event and normal close. Incorrect credentials yielded no inventory
or event. The CONNECT carried no application key and the inner WebSocket
upgrade carried no proxy header.

The native run at `d0f0493` passed 22 unit tests and 71 wire cases,
including a SHA-256 `auth-int` exchange that verified the original POST
body bytes. In each of the three positive native Digest cases the strict
relay accepted all thirteen authenticated operations. The ten Basic
reference cases also passed. The 35 inputs matched the Git revision and
all twelve outputs matched the native receipt. The following SHA-256
digests identify the originals in `artifacts/rust/realtime-assessment/`.

| Receipt | SHA-256 |
| --- | --- |
| Signed reference and earlier ELF, `plain-digest-reference-d0f0493.json` | `8939a80f63fee49c98d5cf042c64308b0853cf797619991a2b25bf6a3b47d1da` |
| Signed reference and corrected ELF, `plain-digest-candidate-d0f0493.json` | `5bc0d2f1a54fb0e4f4836568e4d22d34aeedf67e26dfccf91d8ad3eff1feb9ea` |
| Ten Basic controls, `plain-digest-basic-d0f0493.json` | `5f3b7d21289ffc47e9701f02ed7d99a680aab616b1003f9ffede4f8c7ad7c5a0` |
| Native compiler, graph and tests, `linux-plain-digest-release-d0f0493/result.json` | `81a0e956004a6320f6e8791db7ad8bf643c18fcac868aca02a355211f88bf31d` |

Use `linux_basic_proxy.py --digest` with the archived inputs above and
the original ELF SHA-256. Replay the first two reports with
`replay_linux_basic_proxy.py --digest-reference` and `--digest`
respectively.

### Localized Digest realm

With `charset=UTF-8` and the realm `München`, the signed 3.0.4
client and the Rust executable from the preceding trial sent no Digest
response. At `72cf0a3` Rust reads the selected challenge as UTF-8 and
preserves the quoted realm bytes in its response and hash. A malformed
or unrelated challenge in the same response does not hide a valid one.

The independent relay accepted the corrected Rust response with SHA-256
and MD5, under both strict and shipping-compatible request-target rules.
Each successful paired trial included nine authenticated operations, one
event and a normal WebSocket close. The incorrect-password cases did
not authenticate. The signed client still sent no Digest response.
The two sixteen-case comparisons are stored in the same evidence directory.
Use `--digest --utf8-realm` to replay the corrected candidate comparison.

| Original report | SHA-256 |
| --- | --- |
| Earlier executable, `plain-digest-utf8-before-01.json` | `f192547c780149710c8b4bcdb759aaa4939e9cdde1342712f27764f263b9d63f` |
| Corrected executable, `plain-digest-utf8-after-02.json` | `041a9443fba3ecb45e9ae1ea8361f9aee57ca4346a58a059234ba0c72c973cfd` |
| Ten Basic controls, `plain-digest-basic-after-02.json` | `dea8d39c67158d318b9f0f30c2fa4c508378d032609decae087dbed845cad651` |

At `00443e0` the offline Fedora x64 run passed 24 unit tests, 72 wire
cases, rustfmt and warnings-denied Clippy. The strict relay verified
nonce counts 1 through 13 in the localized case and a normal close
after the event. The 35 original source hashes matched that revision and
the 12 indexed outputs matched the receipt. The executable SHA-256 was
`3cab46d8df9258a1bb4e8f3a4469d460be0bc32adcbeb6bc1234b7c66bddcdf2`.
The original `linux-plain-utf8-source-bound-02/result.json` in the same
evidence directory has SHA-256
`c8c59bc7818bbc1ae053b33b08e7ba8093a1d4000250bd59f196b1e67bfa19eb`.
