# Dependabot PR #43: SocketIOClient 4 compatibility

## Scope and compatibility

PR #43 updates SocketIOClient 3.1.2 to 4.0.5. The initial CI failed because
version 4 removed the transport interfaces used by the hardened realtime
adapters. The integration now implements `Protocol.Http.IHttpClient` and
`Protocol.WebSocket.IWebSocketClient`, registered through the client's service
configuration callback. Each session scope owns and disposes its transports,
including polling-to-WebSocket upgrades and reconnects. HTTP response contents
are detached before disposing the native response because the new upstream
response interface has no disposal contract.

The configured origin, API-key headers, HTTPS default, redirect rejection and
4 MiB HTTP/WebSocket message limits remain enforced. Socket.IO event callbacks
now return tasks. Shutdown first gates new transport factories, attempts graceful disconnect for
at most two seconds, then cancels the connection lifetime and disposes the
current session. Pending HTTP requests and WebSocket operations share that
lifetime. This compensates for upstream 4.0.5's ability to start another
reconnect after disposing its current scope. A failed/canceled initial start
releases its session so a subsequent start can retry. Version
4 removes `ReconnectionDelay`; its randomized retry policy retains the configured
30-second maximum and effectively unlimited attempts, with a 10-second attempt
timeout. There is no configuration or stored-data migration.

## License evidence

The exact NuGet archives identify these source revisions and MIT licenses:

| Package | Source revision | Supplemental notice |
| --- | --- | --- |
| SocketIOClient 4.0.5 | [`9deebcfe8079164d269ec4f22ba58589366014fb`](https://github.com/doghappy/socket.io-client-csharp/tree/9deebcfe8079164d269ec4f22ba58589366014fb) | `SocketIOClient-4.0.5-LICENSE.txt` |
| SocketIOClient.Common 4.0.0 | [`167500202fedc2801e6ee42dfe69b61d0bfc7d25`](https://github.com/doghappy/socket.io-client-csharp/tree/167500202fedc2801e6ee42dfe69b61d0bfc7d25) | `SocketIOClient-4.0.0-LICENSE.txt` |
| SocketIOClient.Serializer 4.0.0.1 | same `1675002` revision | `SocketIOClient-4.0.0-LICENSE.txt` |

Both source revisions contain the MIT license, copyright 2019 HeroWong, without
additional license files in the source archive. Both texts have SHA-256
`e97ff25fc8529385c2a1a12a3a780f07322c32d95f2b00b5a277e7855a900fb8`.
The archives contain only license expressions, so exact-version supplemental
catalog entries preserve the full MIT text in distributions. These permissive
terms are compatible with this repository's AGPL-3.0-only distribution.

The restored net10 graph resolves the Microsoft dependencies to the existing
11.0.0 versions; no additional Microsoft package version is introduced by this
update. The generated offline Flatpak feed also includes five 10.0.3 minimum
versions: Microsoft.Extensions.DependencyInjection, DependencyInjection.Abstractions,
Logging, Options and Primitives. Their exact archives all identify the MIT
license and source revision
[`c2435c3e0f46de784341ac3ed62863ce77e117b4`](https://github.com/dotnet/dotnet/tree/c2435c3e0f46de784341ac3ed62863ce77e117b4).
They embed the same .NET third-party notice (SHA-256
`6d15e10a101c6bfff2ab4429ed061bf76c456fc4b23ad6b03e0d0f8377148a21`),
which the installer retains, but omit the main MIT text. The exact source's
`Dotnet-10.0.3-LICENSE.txt` supplement supplies that text. Only versions actually
present in the candidate feed were added to the catalog. This fixes the first
hosted native build's missing-version notice error.

The former SocketIO.Core and SocketIO.Serializer packages are replaced
by the Common/Serializer packages above.

## Validation

- Focused transport/configuration tests: 18 passed, including the real SocketIO
  client connecting to a synthetic loopback Engine.IO server, polling upgrade,
  API-key headers on both transports, event dispatch, graceful disconnect,
  cancellation followed by restart, and stopping during a failed reconnect.
- Existing synthetic redirect, origin/downgrade and oversized HTTP/fragmented
  WebSocket rejection tests pass against the new transport interfaces.
- License-notice installer collected all three exact new SocketIO archives.
  After the first native build identified missing Microsoft 10.0.3 supplements,
  all 89 archives in its generated candidate feed were checked against the
  manifest SHA-512 values and passed the installer together, including the five
  additional Microsoft versions. Source URLs and notice hashes were validated.
- Full portable Core suite after the lifecycle fix: 486 passed. Linux
  GUI/protocol suite: 53 passed.
- Negative control: removing the lifetime guard makes the stop-during-reconnect
  regression fail because a new connection is accepted after stop. The fixed
  version rejects further transport creation.
- License installer regression suite: 15 passed. `git diff --check`: passed.
- Exact-head hosted CI/CodeQL: pending at this local checkpoint; final results
  belong in the PR body and project status.

No real Immich server was contacted. Windows and native Flatpak validation depend
on hosted CI. This work does not merge PRs, enable automatic merging, publish a
release or alter the license-blocked PR #32.
