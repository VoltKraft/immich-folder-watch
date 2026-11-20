# RW-01 behavior and HTTP compatibility corpus

This corpus freezes selected observable behavior of the .NET reference for the
Rust implementation. It is part of `M-RUST-IMPLEMENTATION-20261114`, with stage
selection and completion owned by [the brief](../project.md) and
[status](../status.md). Passing the reference tests does not establish Rust parity.

## Provenance and isolation

The reference source revision is
`19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc` (shipping 3.0.4), retained unchanged in
the rewrite checkout. The JSON inputs and expected outcomes are authored from
the actual source contracts and executed against production C# APIs by
[`RustRewriteBehaviorContractTests`](../../src/ImmichFolderWatch.Tests.Core/RustRewriteBehaviorContractTests.cs).
They are independent, language-neutral data for the later Rust differential
suite, rather than a substitute implementation of those APIs.

All media bytes, album/asset IDs, credentials, server URLs and files are synthetic.
HTTP ends at an in-memory `HttpMessageHandler`; it never performs DNS or socket
requests. Worker tests use the real worker, filesystem boundary, file readiness
checker, queue and SQLite store with a synthetic Immich client. Unexpected remote
deletion, rename or download fails that fixture. Each test creates a disposable
`ifw-rw01-behavior-*` directory. No installed application host or personal profile
is opened.

The worker harness waits for both initial reconciliation passes, then for durable
batch completion before stopping and joining the worker. It verifies the saved
asset mapping and transfer history after shutdown. Transfer counters alone do
not authorize cleanup. SQLite pools are cleared before removing only the test's
own directory.

## Fixture format and coverage

Each [JSON file](../../rust/tests/fixtures/behavior) has `fixtureVersion: 1`,
`baselineSourceRevision`, `dataClassification: "synthetic"`, and a `cases` array.
Every case has a stable `id` and links to `PAR-*` requirements. Paths in filter
and queue cases are relative to the test's synthetic root. Queue timestamps are
UTC; a null timestamp means the test file does not exist. JSON object property
order is immaterial; ordered request traces, array order, identifiers and numeric
values are significant. Missing/unrecognized operations fail the harness.

| IDs | Contract exercised | Parity |
| --- | --- | --- |
| `BEH-NORM-01`–`06` | Missing, blank, case/whitespace and unknown mode/order inputs; legacy `uploadNew`/`newestFirst` fallback | PAR-01, PAR-03 |
| `BEH-FILTER-01`–`12` | Extension normalization, case handling, recursive globs, ancestor exclusions, filename wildcards and path escape rejection | PAR-03 |
| `BEH-QUEUE-01`–`02` | First attempts before retries, both timestamp orders, missing timestamps last in each attempt group, stable ties, deduplication and ordering before batch limits | PAR-03 |
| `BEH-READY-01`–`04` | Retained-root readable/missing file outcomes, cancellation and invalid timeout | PAR-03 |
| `BEH-HTTPS-01`–`07` | HTTPS default; explicit HTTP exception; rejection of credential/query URLs and non-HTTP schemes | PAR-05 |
| `BEH-API-01`–`04` | Ping route fallback, unreachable service, API-key rejection before further permission probes | PAR-05 |
| `BEH-API-05`–`10`, `20`–`21` | Duplicate/missing named albums, paginated inventory, incomplete/empty pages, aggregate asset/page ceilings, metadata ceiling and malformed asset failure without partial-success results | PAR-02, PAR-05 |
| `BEH-API-11` | All ten permission probes with deliberately invalid IDs, exact methods/bodies and blocking flags | PAR-05 |
| `BEH-API-12`–`13` | Album membership fallback methods/payloads; permission denial does not try alternative routes | PAR-02, PAR-05 |
| `BEH-API-14`–`19` | Unassigned root assets, trash with `force:false`, exact-ID delete/rename, same-name albums do not grant destructive ownership, verifiable new owned ID | PAR-02, PAR-05 |
| `BEH-LEGACY-01`–`03` | Legacy multipart retry and exact device identifier encoding with Unicode/Windows display paths and equal-size, equal-time different contents | PAR-04, PAR-05 |
| `BEH-APPLY-01`–`05` | Invalid local draft and rejected access leave config untouched; save precedes restart; restart failure preserves saved config; cancellation does not save/restart | PAR-06, PAR-08 |
| `BEH-WORKER-01`–`03` | Existing-file startup behavior for all three modes, subsequently created file upload, local preservation, durable mapping and Last Sync | PAR-01, PAR-03, PAR-04 |

HTTP cases specify the exact ordered `steps` (`method`, absolute API `path`,
synthetic response `status`/`body`, and optional `requestJson`). Every request must
stay at `https://immich.example.test` and carry the synthetic API key. Negative
cases retain request-assertion exceptions separately: production transport-error
handling cannot swallow an incorrect request and accidentally pass the case.
The handler must consume exactly the expected number of steps.

The legacy upload vectors contain Base64 bytes, an exact display path, UTC
modification time, decimal-string .NET ticks, uppercase content SHA-256 and the
expected lowercase final identifier. The independent vector calculation is:

```text
lowercase_hex(SHA256(UTF8(displayPath + "|" + decimal(byteLength) + "|"
    + decimal(dotNetUtcTicks) + "|" + uppercase_hex(SHA256(fileBytes)))))
```

The test creates a real file with that timestamp and verifies the C# handle's
tick readback. It invokes the public upload method with an explicitly retained
file capability, a synthetic display path and an in-memory 422 legacy-server
response. Both transmitted bodies must contain the original bytes; the second
must carry the fixed expected ID and `deviceId=immich-folder-watch`. The handler
attempts an equal-size/equal-time leaf replacement between requests. Linux
retains the original file object; Windows may safely refuse replacement while
the handle is open. This is not evidence that all directory races are covered.

## Run and recorded evidence

From the repository root with the SDK in `global.json`:

```bash
dotnet test src/ImmichFolderWatch.Tests.Core/ImmichFolderWatch.Tests.Core.csproj \
  -c Debug --artifacts-path artifacts/rust/behavior \
  --filter FullyQualifiedName~RustRewriteBehaviorContractTests \
  --logger 'trx;LogFileName=rw01-behavior.trx' \
  --results-directory artifacts/rust/behavior/results
```

The fixture locator walks upward from `AppContext.BaseDirectory`, then uses the
compiled test-source location. For a relocated test binary, set
`IFW_COMPATIBILITY_REPOSITORY` to the checkout containing `rust/tests/fixtures`.
An invalid explicit location fails; it never substitutes another corpus.

On 2026-11-14, all **63 cases passed, 0 failed, 0 skipped**, on native Linux x64,
SDK 10.0.401/runtime 10.0.12. The executable was the existing repository-local
`artifacts/flatpak-local-2.11.2/sdk/dotnet`; the CLI profile was isolated under
`/tmp/ifw-rw01-behavior-cli`. The test run required local test-runner IPC outside
the restricted sandbox. Report:
`artifacts/rust/behavior/results/rw01-behavior-linux-x64.trx` (generated, ignored).
The build reported the pre-existing `CS0618` D-Bus API warning in
`DBusBackgroundPortalRequest.cs`; no new dependency or production source changed.
JSON parsing/unique-ID checks cover all nine files, and `git diff --check` passed.

An initial run exposed two harness mistakes (a progress counter describes the
current operation, not lifetime transfers; a single-page oversized inventory
fails parsing before the aggregate-limit branch). The final harness waits for
current durable completion and exercises the aggregate limit across two valid
pages. No production behavior was changed to make fixtures pass.

## Remaining evidence and reuse limits

The corpus is a compatibility baseline, not complete PAR acceptance. Existing
regression suites remain necessary and are not replaced by these compact vectors:

- [`ImmichTransferSecurityTests`](../../src/ImmichFolderWatch.Tests.Core/Services/ImmichTransferSecurityTests.cs)
  exercises streaming/decompression/inactivity/download limits and failure cleanup;
  [`RealtimeTransportSecurityTests`](../../src/ImmichFolderWatch.Tests.Core/Immich/RealtimeTransportSecurityTests.cs)
  covers actual local transport redirects, origins and message bounds.
- [`FolderWatchWorkerPersistenceTests`](../../src/ImmichFolderWatch.Tests.Core/Services/FolderWatchWorkerPersistenceTests.cs)
  and its partial files cover unchanged reconciliation, download ordering,
  tombstones, write failures, repairs and deletion concurrency.
  The separate [storage corpus](rw01-storage-contract.md) owns persisted codecs
  and schema evidence.
- [`AlbumOwnershipSecurityTests`](../../src/ImmichFolderWatch.Tests.Core/Services/AlbumOwnershipSecurityTests.cs),
  [`FolderWatchWorkerAlbumSecurityTests`](../../src/ImmichFolderWatch.Tests.Core/Services/FolderWatchWorkerAlbumSecurityTests.cs)
  and the native filesystem suites remain required for ownership revocation,
  incomplete local inventories and full root/parent/leaf adversarial coverage.
- File readiness here means the baseline's authorized file can be opened for
  reading. It does not claim a two-sample stable-size test or protection from a
  concurrent writer merely because the read succeeded.
- Save/Apply and worker shutdown tests do not validate a desktop window, tray,
  portal, autostart or cross-session instance handover. Native GUI accessibility,
  IME/DPI, native notifications, package installation and all Windows/ARM64
  execution remain separate stage gates. Notifications are a new requirement;
  there is no equivalent proven Windows notification oracle to inherit.
- The synthetic client only controls the test boundary. Rust must implement real
  production HTTP/realtime/filesystem/platform adapters; passing against a test
  double cannot satisfy a missing production feature.

When reference behavior changes, retain the old fixture IDs and record the
source revision and compatibility decision before updating expectations. Run both
reference and Rust consumers against the same reviewed corpus. Do not regenerate
expected outputs blindly from a candidate implementation.
