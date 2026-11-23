# RW-01 legacy configuration and storage corpus

The [C# oracle](../../tools/RustCompatibilityOracle/Program.cs) invokes the shipping
`AppConfigLoader`, `AppConfigWriter`, `SyncAccountScope` and `SqliteSyncStateStore`.
It is development tooling, not part of the Rust application. It introduces no
package dependencies: its only project reference is the existing Core library.
The behavioral source baseline is `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`.
Each generated manifest records hashes of the actual owning C# sources, so a
changed baseline causes verification to fail pending review.

All database files and configuration parsing take place in a unique temporary
directory. On Linux that directory is owner-only. No installed profile is read,
no worker starts, no media path is opened and no network request is made by the
oracle. The server names use reserved `.invalid` domains and credentials are
explicit synthetic strings. SQLite pools are closed before temporary cleanup.
Build/restore tooling may contact the configured NuGet source independently.

## Commands and evidence boundaries

Run from the repository with the exact SDK from `global.json`:

```text
dotnet run --project tools/RustCompatibilityOracle/RustCompatibilityOracle.csproj -- export artifacts/rust/oracle
dotnet run --no-build --project tools/RustCompatibilityOracle/RustCompatibilityOracle.csproj -- verify artifacts/rust/oracle
dotnet run --no-build --project tools/RustCompatibilityOracle/RustCompatibilityOracle.csproj -- verify rust/tests/fixtures/legacy
```

`export` writes deterministic UTF-8/LF text beneath the selected directory's
`linux/` or `windows/` subdirectory. `verify` independently regenerates every case
in a fresh temporary profile and compares all bytes, source hashes and file names.
It fails for missing, changed or additional files. Never manually repair generated
fixtures. Regenerate only after inspecting the source change and expected behavior.

Set `IFW_ORACLE_EXPECT_ARCH=x64` or `arm64` in native CI lanes. The program refuses
a mismatched process or operating-system architecture before creating fixtures.
The console reports both architectures and the executing .NET runtime. This guard
does not establish GPU, screen-reader, desktop or installer acceptance.

The reviewed [Linux corpus](../../rust/tests/fixtures/legacy/linux/manifest.json)
and [Windows corpus](../../rust/tests/fixtures/legacy/windows/manifest.json)
were each reproduced on native x64 and ARM64. CI checks out the C# reference
sources with the line endings used to compile each original oracle, LF on Linux
and CRLF on Windows. The generated fixture files themselves use LF on both.
On a local checkout with different source bytes, inspect the manifest mismatch
or use a disposable native checkout with the CI settings. Native Windows
path parsing includes drive/UNC strings. Access to an actual UNC share still
requires a separate filesystem test. See the [run evidence](rw01-native-reference.md).

## Fixture mapping

| Fixture | Executed reference contract | Parity mapping |
| --- | --- | --- |
| `config/*.input.yaml`, `*.written.yaml`, `*.expected.json` | Five cases: absent/default fields, legacy extension fallback, null sections, YAML-sensitive scalars/Unicode/backslashes, and aliases. Compare editable versus runtime normalization and C# writer/readback. | PAR-01, PAR-03, PAR-06, PAR-07 |
| `identities.json` | URL trimming without case/port canonicalization, direct API-key whitespace semantics, UTF-8 SHA-256, .NET invariant uppercase including sharp-S/Turkish/sigma/combining and supplementary characters. | PAR-01, PAR-04, PAR-08 |
| `sqlite/path-vectors.json` | Native root/trailing-separator/dot-segment handling, relative separator handling and case-sensitive/insensitive keys. Windows execution includes UNC strings. | PAR-04, PAR-08 |
| `sqlite/{sensitive,insensitive}.sql` | Schema version 1 and all four tables, generated from actual SQLite metadata and values after production API writes. | PAR-02, PAR-04 |
| `sqlite/*.expected.json` | C# readback plus raw SQL column names/values; numeric enums, nullable asset ID, tombstone expiry, large 64-bit size, UTC timestamps, PascalCase repair JSON and uppercase SHA-256. | PAR-04 |
| `sqlite/*.legacy-schema-cases.json` | Version 0/1 crossed with all eight combinations of missing optional tables; preserve entries, backfill transfer history only once, exclude tombstones from backfill. | PAR-04 |
| `sqlite/*.operations.json` | Inclusive tombstone expiry; conflicting repair intent and compare-and-swap failure retain the journal; successful completion changes mapping/removes journal without advancing transfer history; exact-ID removal and account-scoped authority revocation. | PAR-02, PAR-04 |
| `sqlite/*.wal-backup.json` | SQLite backup API includes a committed, nonempty WAL and passes `integrity_check`; preserved history read through C#. | PAR-04, PAR-09 |
| `sqlite/future-version.observed.json` | Actual baseline rejection of schema 999, including journal-mode mutation described below. | PAR-04, PAR-09 |

`$PROFILE` in runtime configuration expectations stands for the isolated directory
containing `config.yaml`; native path separators remain significant. JSON integers
must be read losslessly: one fixture intentionally exceeds JavaScript's exact
integer range. SQL uses seven-digit UTC round-trip timestamps; repair JSON retains
the distinct System.Text.Json timestamp rendering. Do not rewrite either format
using a generic RFC3339 default.

The SQL snapshots are deterministic interchange inputs, not byte-identical SQLite
files. Importing them into fresh databases and reading them with the C# APIs is
part of every oracle run. No physical database-page reproducibility is claimed.

## Baseline discrepancy that Rust must improve

The current C# store calls `PRAGMA journal_mode=WAL` before checking
`PRAGMA user_version`. Its schema-999 input is rejected and its sentinel/version
are retained, but the test observes `delete` becoming `wal` and the file bytes
changing. This is an observed baseline limitation, **not** permission for Rust
to mutate an unsupported format. The Rust migration preflight must open unknown
formats read-only and leave the database and sidecars unchanged before refusing
to synchronize. Keep this stronger acceptance test separate from C# parity.

Likewise, preserving `owned_albums` in interchange is not authorization to reuse
it after process start. Startup must revoke stale authority for the active account
before destructive operations. The oracle tests the storage operation; the worker
startup sequence requires the separate behavior/security corpus.

## RW-03 round-trip and recovery contract

1. Import each native SQL snapshot into a fresh synthetic profile. Rust must read
   all columns, history and journals without converting keys or timestamps.
2. Apply every operation case using Rust and export logical SQL state. Read that
   state with the C# store and compare its expected entries, repair codec,
   ownership and monotonic history. Test C# writes read by Rust and Rust writes
   read by C#; existing C# export/import alone does not prove the latter.
3. Derive old-schema inputs from the base snapshot by dropping the exact optional
   tables listed in each case, then setting its `UserVersion`. Assert the recorded
   initialization/backfill outcome and repeat startup after a metadata-only change.
4. Exercise WAL-aware backup after quiescing the engine, permission preservation,
   process termination at each boundary, failed writes and full-disk recovery.
   The currently executed backup primitive test proves only WAL inclusion and
   integrity; it does not prove application-level quiescence or crash recovery.
5. Test rollback after actual synthetic uploads, downloads, deletions and repairs.
   Restoring an earlier database cannot undo filesystem or Immich side effects.
   These activity, platform and installer gates remain RW-03/RW-07 work.

No Rust production codec, migration, cross-session writer exclusion or installer
result is claimed by this corpus. The [rewrite plan](../rust-rewrite-plan.md#data-compatibility-and-migration)
and [filesystem contract](../watch-root-security.md) remain binding.

## Download activity and the latest backup

The [worker test](../../src/ImmichFolderWatch.Tests.Core/Services/FolderWatchWorkerPersistenceTests.ActivityBackup.cs)
captures online backups before and after one completed download. The shipping
worker reconciles the synthetic `Camera` album and writes six bytes to
`photo.jpg` in a newly created watch root. The fixture waits for the persisted
mapping and account Last Sync, captures the second backup, drains the worker
and reads the first backup alongside the existing file. The older database
contains neither the mapping nor the transfer history. Reading it leaves the
downloaded file in place.

A second worker opens a copy of the latest backup and reconciles the same
album and live watch root. It must retain both original time stamps, the
downloaded file and its native file times, with zero additional transfers.
The peer supplies synthetic album metadata and asset bytes in-process.
The two backups, original file, JSON observations and passed test result
can be independently checked after relocation. The verifier checks all four
table definitions against the reviewed SQL corpus, reads all thirteen mapping
columns, and matches the observer's digest in that specific xUnit execution.
Both executing assemblies identify the source revision. The C# test measures
native file times before export. ZIP extraction can change filesystem metadata.
[Detached readback](../../tools/RustCompatibilityOracle/verify_activity.py) · [Local and hosted commands](../development.md#download-activity-backups-and-restart).

This reference establishes the legacy result for a completed synthetic
download. The installed candidate still needs to preserve external effects
and history across its own uploads, downloads, deletions and repairs.

At `cf38f1a` each of the four native reference jobs ran the case on .NET
10.0.15. The two Ubuntu targets passed 567 tests each. Each Windows target
passed 558 and skipped the same nine Linux-specific tests. All four original
TRX files bind the activity digest to the passing test. Independent SQL
readback verified all eight original backups. Each worker requested one album
listing on each start, with transfer counts of one download followed by zero.
The four-archive readback SHA-256 is
`4bf1149068f1cfd01393ced5c0a015d2f8aaff2af9169512511dc7da4072b55d`.
[Linux x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45168670336/artifacts/14815617605) · [Linux ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45168670336/artifacts/14816356054) · [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45168670336/artifacts/14815577866) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45168670336/artifacts/14816211257).

The [native Rust backup trial](../../tools/rust-qa/storage/README.md#restore-after-a-synthetic-download)
uses the same two worker reconciliations with a private file exchange.
The earlier C#-only reference can still be replayed from its original archive.

At `ba02f8b` the two-language trial passed on Fedora x64 with both
real processes. Rust rejected the empty pre-download backup and returned
a new SQLite backup of the post-download donor. C# reopened those exact
bytes, reconciled the original album and retained the original file without
another transfer. Detached review reproduced the saved readback byte-for-byte
(SHA-256 `24f53c85e496171601ea4e7e3b2b257ab4c142a12f4b59884bedbdf2f5b5f7c9`),
compared the complete schemas and rows, and checked all 300 evidence hashes.
The result is under `artifacts/rust/worker-backup-native-ba02f8b/`.
[Native trial on Windows and Ubuntu](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804585).

The same trial passed natively on Windows and Ubuntu, x64 and ARM64, at
`ba02f8b`. Each Rust process refused the stale donor with exit code 1.
Each second C# worker listed the album, completed zero transfers and
retained its original mapping, account history and photo. Independent
readback reproduced the four original reports byte-for-byte and checked
all 1,198 indexed files. The local four-host summary under
`artifacts/rust/hosted-worker-backup/45172804585/source-bound-readback.json`
has SHA-256 `d43cd9d15a1c482739f252998adf33b75afd931ab7a43346defe897ab9583cdf`.
The hosted archives retain executable digests, source and build logs. The
independent hosted check covered the archived databases, media, sources
and test reports. The executable bytes were available for the Fedora check.
[Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804585/artifacts/14817207902) · [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804585/artifacts/14818635061) · [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804585/artifacts/14817853842) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45172804585/artifacts/14818133568).

## Peer content after a synthetic upload

The C# worker at `c0abae3` uploaded eight binary bytes from its opened
watch-root stream. A synthetic peer stored them under a separate directory
and derived the asset ID from their SHA-256. The restarted worker opened
a copy of the latest SQLite backup, reconciled the peer's retained asset
and preserved the mapping, Last Sync and local photo. Both cycles
completed without a trash request or recorded album mutation. Test-only
controls submitted a trash request before the first stop and an ID-based
album rename during restart. Each failed the corresponding assertion.
The clean Fedora x64 TRX contains the peer digest and asset ID. The fixture
removes its temporary upload databases and media after the test.
[Upload reference](../../src/ImmichFolderWatch.Tests.Core/Services/FolderWatchWorkerPersistenceTests.UploadActivity.cs).

At `9efe6f4`, the test passed on all four native hosts. Each independently
replayed TRX identifies the eight uploaded bytes retained by the separate
peer. Reconciliation after restoring SQLite preserved the local file and
remote asset, with zero repeat transfers, trash requests or recorded ID-based
album changes. That peer did not record membership writes or name-based
album changes.
Ubuntu passed 568 tests on each architecture. Windows passed 559 on each
and skipped the nine Linux-only tests. The four-archive readback SHA-256
is `9368522d6c4834f6b5d16c8d3c67372f40b315b43d4e0412723681709ecb2921`.
[Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45175252132/artifacts/14819601003) · [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45175252132/artifacts/14819470624) · [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45175252132/artifacts/14818820858) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45175252132/artifacts/14818925892).

The cross-language upload fixture supplies the original and post-upload
snapshots to Rust and restarts the shipping worker from Rust's returned
bytes. The synthetic peer implements every shipping asset-client call and
records unexpected mutations before returning an error. On Fedora x64 the
first worker uploaded once, the second made zero transfers, and the peer
retained the eight bytes and the same asset ID. Both workers stopped with
an empty rejected-request record. Ten deliberately injected mutations were
detected even when their caller caught the peer error. The local run used
working-tree sources. Eight earlier native download archives reproduced
their original reports byte-for-byte. [Native reproduction and replay](../../tools/rust-qa/storage/README.md#restore-after-a-synthetic-upload).
