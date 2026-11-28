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
