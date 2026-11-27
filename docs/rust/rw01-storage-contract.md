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

The clean Fedora x64 run at `c4b876c` repeated both worker exchanges
offline. The second worker opened the Rust backup, retained the mapping
and Last Sync, and observed the original peer bytes. Replay verified both
complete reports, 318 indexed files and 154 exact project sources. The
upload backup SHA-256 was
`0a570ff0f671119d060c0cfe14e245d3f9a1658fc5f9f2c4562c4915a8009d2f`.
The original records and detached readback are in
`artifacts/rust/worker-backup-native-c4b876c/`.

At `653f255` both exchanges passed on Windows and Ubuntu, x64 and ARM64.
The eight replayed reports matched byte-for-byte. Each archive contained
154 archived Git sources. The detached check verified 1,270 indexed
files across the four archives and confirmed zero transfers after each
restart. Every receiving peer retained the original eight bytes and
recorded zero rejected calls. The four-host readback has SHA-256
`6099697c7aa98840aeab7bef95ac2ffc48728e998b29c32cf62243e6b4a75709`.
The C# reference suite passed 569 cases on each Ubuntu host and 560 on
each Windows host, with nine Linux-specific skips.
[Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595626/artifacts/14839740550) · [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595626/artifacts/14838732149) · [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595626/artifacts/14839217031) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595626/artifacts/14838078683) · [Native reference suite](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45216595572).

## External state after deletion and timestamp repair

The repair reference interrupts the C# worker after it changes the
synthetic photo's native timestamp and before the database records
completion. It retains three standalone backups. Restoring the first
leaves the photo's repaired timestamp in place. A new worker reading
the pending backup completes the journal, preserving the original
mapping's transfer date and the separate account Last Sync.
[Repair fixture](../../src/ImmichFolderWatch.Tests.Core/Services/FolderWatchWorkerPersistenceTests.RepairBackup.cs).

The deletion reference downloads a synthetic photo through the shipping
Immich client, then removes the local copy while the worker runs. The
client requests trash for the exact asset with `force=false`. Its
in-process peer moves the nine original bytes to a separate directory.
Reading the stale mapping leaves both the local and peer album
directories empty. Restart from the post-deletion backup retains the
tombstone and reconciles the empty album without a second trash request.
The installed Rust candidate's own repair and deletion remain to be
exercised. [Deletion fixture](../../src/ImmichFolderWatch.Tests.Core/Services/FolderWatchWorkerPersistenceTests.DeletionBackup.cs) · [Independent database and media reader](../../tools/RustCompatibilityOracle/verify_rollback.py).

At `e558b42`, both cases passed on Fedora x64 and all four hosted targets.
The native repair journal contained zero, one and zero rows in the three
successive backups. The transfer date stayed February 4, 2014, and the
account Last Sync stayed February 5. The photo's modification time was
February 4, 2004 on Ubuntu and February 6, 2004 on Windows. Windows also
preserved the February 4 creation time. Each deletion case retained a
single tombstone and the same nine peer-trash bytes, with one trash
request before restart and zero afterward. Detached replay matched
the eight reports, the original DLLs identified by the tests and every
one of the 49 archive entries on each target. The four-host receipt
SHA-256 is `9735ccd5af42688df6328bdfabc5a4527260b3e0a20725dac136e5768756e17f`.
[Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45220169874/artifacts/14840960347) · [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45220169874/artifacts/14841840102) · [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45220169874/artifacts/14839659957) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45220169874/artifacts/14839378878).

The cross-language repair trial gives Rust the pending journal. SQLite's
backup API must preserve the exact journal string, its matching original
entry, and the separate account history. The deletion trial gives Rust the
post-deletion tombstone. Both reject an earlier database before producing
an output. The second shipping worker identifies the returned digest in
its xUnit result. The detached reader compares all four tables and checks
the photo or peer trash contents across both workers.
[Replay commands](../../tools/rust-qa/storage/README.md#restore-after-a-deletion-or-interrupted-repair).

On Fedora x64 the independently reviewed working tree passed these two
exchanges alongside the download and upload. The two pure C# controls
also passed. Thirteen changed donors were rejected. A valid journal with
different JSON whitespace survived byte-for-byte. The detached reader
rejected four inconsistent receipts and reproduced 24 earlier native
upload and download reports. The reviewed four-exchange receipt has
SHA-256 `c2975117c3966efa6db6f27afe9bbfe78151cef5d38c4e68b1b3cbad784a3900`.

### Four worker restarts on each native target

At `1904be715b0615ba496ca177e5fe3cddf2971d7a` the shipping C# workers
resumed on all four systems after Rust backed up their SQLite state.
The four initial states followed an actual download, an upload, a propagated
deletion and an interrupted timestamp repair. Each of the 16 successful xUnit
executions identified the exact database returned by Rust. Independent replay
recovered its four tables, matched all 16 reports byte-for-byte and checked
158 first-party sources per archive.

The upload peer retained all eight bytes and the asset ID. The deletion peer
retained nine bytes in trash and received no second deletion request. The
pending repair was still present in the returned database. The worker
completed it with the original mapping, file timestamp and account history.
The detached four-host readback covers 1,454 indexed files and has SHA-256
`3d78051c4578db4aba46a43c54cfa1f21f81d59dca9586e989fd302ff27117e7`.
[Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321106/artifacts/14847212368) · [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321106/artifacts/14846268177) · [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321106/artifacts/14847716353) · [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230321106/artifacts/14847288755).

The separate C# reference suite passed 571 cases on each Ubuntu target and
562 on each Windows target, with nine Linux-specific skips on each Windows
host. Its original databases, retained media, loaded assemblies and xUnit
results reproduced the reference readback with SHA-256
`4120b41b8164540b54ba562f97b1046f9a21e3b663b6869c11720540a4cbe27f`.
Rollback after the installed Rust sync engine's own activity remains open.
[Native C# reference run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45230320974).

At `f155b65` all four targets repeated the four worker restarts. Detached
replay verified 1,466 indexed files, compared 161 first-party source
files per archive with the measured Git revision and recovered all 16
distinct xUnit executions. Each shipping worker consumed the Rust backup
identified by its returned bytes after download, upload, propagated deletion
or interrupted timestamp repair. The combined readback SHA-256 is
`05b00b8ec4a85bd3b3ab0768c5e81b7688ba4a84d44751154aca773655e1813c`.
[Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937394/artifacts/14982900992) ·
[Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937394/artifacts/14982163282) ·
[Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937394/artifacts/14982193656) ·
[Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45525937394/artifacts/14981499821).

### Native worker recovery at 0bb39bf

All sixteen C# worker restarts passed on the two Windows and two Ubuntu
hosts at `0bb39bf`. Each worker consumed the exact `returned.db` from
the native Rust executable after a download, upload, deletion or
interrupted timestamp repair. Detached replay checked the original
database identity, all four tables, HTTP requests, retained media or
trash bytes and the completed timestamp repair. The two casing profiles
also retained the committed WAL with the original main file still in
place when Rust took its online backup. There were 40 C# storage readback
checks on each host.

Each Windows archive indexed 366 files and each Ubuntu archive 367.
All 161 first-party sources per archive matched the checkout. Under
`artifacts/rust/hosted-worker-backup/45874234282/`, the combined report
`source-bound-four-exchanges.json` has SHA-256
`b6e90060b46105cc2b26c6f8e66c111edfb599d9843710e52b7179ddf0ca0fa0`.
[Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234282/artifacts/15145060676) ·
[Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234282/artifacts/15144930870) ·
[Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234282/artifacts/15144143135) ·
[Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234282/artifacts/15144328383).

### Installed Fedora worker resumes from a live Rust backup

On Fedora x64 at `3709869` the original signed 3.0.4 Flatpak uploaded
a 69-byte PNG to the private peer. A read-only SQLite connection kept the
pre-upload snapshot open. Before the response, the Rust backup helper
refused the empty history. After 3.0.4 committed, the main database was
still 4,096 bytes and lacked the new entry. The 65,952-byte WAL held the
committed state. Rust opened the live database read-only, used SQLite's
online backup API and finalized a standalone database. Replaying the
original main file and WAL reproduced the Rust output's ten schema
objects, four tables, all columns and ROWIDs.

After the signed app quit, the observer preserved the original database
and companions, installed a separate copy of the returned bytes at the
profile's normal database path and held that file open. The next signed
apphost (PID 1492) opened the same device and inode as the pre-launch
descriptor. Its first reconciliation queued zero changed files. Adding a
second PNG produced the next successful upload. Across both processes the
peer recorded four POSTs to the asset route, including one empty permission
check and one accepted image per process. The original file was absent
from the second process's requests. After Quit, the original mapping and
the new mapping reopened with ROWIDs 1 and 2.

The `same-id-mn3lm5yd/result.json` SHA-256 is
`b3f150b7abdb021f59f4b15c12f3524a075cc7f0af3a8e6d8091091e4160c9b9`.
The consumed Rust database has SHA-256
`4e372933e6aa2c8c691f119d1bf55687f441645c1322823f2e9c09cc026e7f0c`.
Independent replay verified all sixteen WAL frame checksums and commit
boundaries. After frame 11 the tables were empty. Frame 14 committed the
mapping and frame 16 added the account history. The 53 indexed originals
included all four request bodies and the signed installation evidence.
The detached `restore-readback-mn3lm5yd/readback.json` SHA-256 is
`a022e9e6e6624d7482ea83fe70a72b8b782a7ed76921d22927c5fece5ad8e000`.
The configured writer in this trial was the signed C# application. Installed
rollback after the Rust synchronization engine's own activity remains open.
[Reproduction](../development.md#installed-flatpak-worker-backup-on-fedora-x64) ·
[Installed process and restore observer](../../tools/RustCompatibilityOracle/installed/interop/installed_backup.py) ·
[Native Rust helper](../../tools/rust-qa/storage/examples/installed_upload_backup.rs).

### Native Linux handover and backup observer

The observer now supports native Ubuntu x64 and ARM64 as well as the
existing Fedora x64 fixture. In the Fedora regression the Rust primary
and its direct inventory worker retained their identities at five checks
across the signed secondary's launch. In the opposite order the signed
primary held its upload connection when the Rust secondary exited.
The first mapping was visible in the live WAL when Rust took its backup.
On ordinary startup the next signed apphost opened the returned database,
kept the first mapping and uploaded the second synthetic PNG.

The `same-id-0cv5enwx/result.json` SHA-256 is
`9921248c5e1d148a18ebbabc2a618a9155487f45fb23c669042ce2a17f5c152e`.
The returned database has SHA-256
`9e43543311106644ba7db874c36bb5bbba3883f5e3e889d7b82f9426c4c9f172`.
Detached readback verified 52 indexed files, both image bodies, 16 WAL
frames and the two final mappings with ROWIDs 1 and 2. Its report under
`detached-worker-tl1r89h2/readback.json` has SHA-256
`22580006cb1b2c68c9d0c4d353fc7d5c4d006060419de58d0ba89ca1b7e71d36`.
Both branches were uninstalled. A clean-checkout repeat at `0bb39bf`
again retained the first asset, committed the second and passed SQLite
`quick_check` on both the returned and final databases. Its result under
`same-id-_burq258/` has SHA-256
`86596a8f631e2a5ef6babc3dce0239e868a3e2ab5ce6ab737900f3340f116746`.
[Native workflow and archive layout](../development.md#installed-worker-handover-on-native-ubuntu-runners).

On Ubuntu x64 and ARM64 at `0bb39bf`, both signed primaries opened and
quit. Both Rust GUIs subsequently started their inventory worker and
hid their original window. The observer then tried to arm its directory
descriptor to observe a real worker read. Ubuntu's Python 3.12 lacked
`fcntl.F_SETOWN_EX`. Both trials exited at that point and removed their
two Flatpak refs. Neither reached the configured upload or backup.
The native Linux command selects the observer thread for signal delivery.
Python added those constant names in 3.13.
[Python fcntl versions](https://docs.python.org/3/library/fcntl.html) ·
[Linux UAPI](https://github.com/torvalds/linux/blob/v6.8/include/uapi/asm-generic/fcntl.h) ·
[Ubuntu x64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228/artifacts/15145705117) ·
[Ubuntu ARM64 original](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45874234228/artifacts/15144839474).

The observer now uses the Linux x64 and ARM64 ABI values when the Python
names are absent. On the existing x64 Noble 24.04 userspace, Python
3.12.3 reproduced the original exception. With the correction, the
kernel returned the selected thread ID for the opened directory. Reading
the directory delivered one `SIGRTMIN` to that thread. Reading the parent
or reading the watched directory again delivered none. Fourteen local
controls passed under Noble and Fedora, and the full Fedora installed
handover passed. Under `artifacts/rust/hosted-installed-handover/45874234228/`,
`noble-fd.json` has SHA-256
`2813b98170b1f86616efddadf3ce90343bcfc8792347b7ebf2bdcf04270e1777`.

At `3d67a46` the entire x64 handover also passed inside an isolated
Noble userspace with its own Python 3.12.3, Flatpak 1.14.6 and system
libraries. This used the Fedora host kernel and local native x64 builds
of the Rust GUI, inventory worker and backup helper. The original worker
survived the signed launch. The two real directory reads reached the
selected thread. After restarting from Rust's backup, the signed app
retained the original upload and committed the second one. Both installed
refs were removed. Under `artifacts/rust/shipping-flatpak-interop/`,
`noble-userspace-bgdqbgvu/trials/same-id-smagh1_l/result.json` has SHA-256
`fd50defb6eeb7d5ddeb1324ff3bc96856006eafea78c8b488809c8a835e28f77`.
The detached replay of both multipart requests, all 16 WAL frames and
the final ROWIDs has SHA-256
`b760ac22946ea03795856a473e92d3e016d9f9f68c9d6b07c6eb6892a7c33d46`.

### Installed Ubuntu worker restart at 3d67a46

On the native Ubuntu 24.04 x64 and ARM64 runners, Flatpak 1.14.6 installed the
original signed 3.0.4 app and the test branch. Five observations followed
the same Rust GUI and inventory worker through a shipping launch. In the
reverse order the signed worker uploaded `signed-worker.png` to the isolated
peer. Rust backed up its live SQLite database. After restart the shipping
worker kept that asset and uploaded `after-restore.png`. Both refs were
removed from the private installation.

Independent replay verified the signed commit, native executable architectures,
52 indexed evidence files, both multipart image bodies, 16 WAL frames, and
ROWIDs 1 and 2 in the final database. The local review files are under
`artifacts/rust/hosted-installed-handover/45877580663/`.

| Native archive | Rust GUI / worker PID | Installed result SHA-256 | Detached review SHA-256 |
| --- | --- | --- | --- |
| [Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45877580663/artifacts/15148705376) | 181 / 192 | `8ff16a133822d98bed5b8ac69fb8f9ca22311365ad374de2a1ab9547e2ad2199` | `1a01bd30c084c31a0dd07023213a0f33c1d2c11e8b22813b3af3864bbd8f7946` |
| [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45877580663/artifacts/15146774111) | 179 / 190 | `45aff5eb6dec079fc647aed77d46b3dc1d64ea43dd1fbb875dee0b694108f4a1` | `a55948eb7da40682c2d6412462da675f9f1f1e9e61f32f47bdb408fe8f8e3921` |

The combined `comparison.json` has SHA-256
`2fbe453f1342b12e84fddc3992e3ee7e9ecdadce6985db25354b7a2c85dc0678`.
Both hosts recorded the same two image byte sequences as the Fedora run.

### Menu shutdown after an installed Linux restore

At `10ab0b8` the native Ubuntu ARM64 observer read both committed rows
from the restored database before clicking Quit. The private D-Bus daemon
reported that the recipient disconnected while the call was awaiting a
reply. The observer stopped there. The following revision, `1a62d5c`,
completed the original restore trial on both Ubuntu architectures.
[Initial ARM64 job, step 64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45963591552/job/140386886900#step:64:1) ·
[Repeat on Ubuntu](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45964876195).

The revised observer resolves the menu owner's unique bus name. It
checks the owner's process against the session-bus proxy reached through
the original signed GUI's mounted socket, then sends the click to that
owner. It records whether the menu acknowledged the call or the bus
reported the recipient disconnecting. The original process must exit
normally, its menu must disappear and a configured worker must log its
shutdown after the click. The restore trial then opens the final database
and verifies both mappings and the state of the two files.
[Menu observer](../../tools/RustCompatibilityOracle/installed/interop/gui_refusal.py) ·
[Installed database checks](../../tools/RustCompatibilityOracle/installed/interop/installed_backup.py).

On Fedora x64 the installed signed app acknowledged all four clicks. The
private bus identified four separate proxy processes. Each matched the
socket peer seen from the corresponding GUI. The two configured workers
logged their shutdowns and the final database passed SQLite's
`quick_check` with the original and new asset mappings at ROWIDs 1 and 2. Both test
refs were removed. The separate same-ID and different-ID probe runs also
confirmed a normal signed exit. A private D-Bus regression exercised the
recipient disconnecting after it received the click and before replying.
All 18 regression tests passed.

The working-tree test used base `483f053` and archived its exact sources.
Under `artifacts/rust/shipping-flatpak-interop/same-id-0_8jvfk6/` the
result has SHA-256 `6cdd171686a03aad6b5dd35f485f6b8198669a3e8238634b2200809a4875cfcd`
and the observer source ZIP has SHA-256
`0279a18cb9e12e6c676091ff7eacb0476fb1767529d8c70f992c5182674e059c`.

At `cd15d1c` both native Ubuntu 24.04 hosts completed the signed
handover. All four menu owners on each architecture returned a positive
reply to their own click. Each configured worker logged shutdown. Detached
replay verified the 16 WAL frames, the original mapping at ROWID 1 and
the newly uploaded file at ROWID 2 on both hosts. Each run removed both
Flatpak refs and released its processes, sockets and bus names.

| Native archive | Original ZIP SHA-256 | Quit call serials, in run order |
| --- | --- | --- |
| [Ubuntu x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45980883765/artifacts/15191566144) | `8f6abbf6d1c5ab7d256a25891d517121ab849958db0cca8ac1831deb3b5b2b78` | 9, 168, 176, 184 |
| [Ubuntu ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45980883765/artifacts/15191331698) | `f83ce900dffad90a252c2017781f96fbd981d66463abed9b32bc463566072375` | 9, 182, 190, 198 |

The two-architecture readback under
`artifacts/rust/hosted-installed-handover/45980883765/comparison.json`
has SHA-256 `a2f9f428df05f99ca9f8e94914821a7e268ac5ddb69e231d1c03d9cde1c89ff9`.

### Installed Windows worker restart at 2dd5f93

Both original Windows 3.0.4 packages uploaded the first synthetic PNG to
the private peer. On each host the held HTTP request matched the installed
WPF process's native IPv4 connection. The original database main file
alone contained no upload row. Its 16 WAL frames restored the committed
first row. Rust refused the empty pre-upload state, then returned a
standalone database with the same schema, rows and ROWIDs as the live
main/WAL pair.

On x64 the original process (PID 4720) quit via the verified native
menu. The next installed process (PID 6016) opened the returned database
and uploaded only the second PNG. Both image requests received HTTP 201.
The final database preserved the first mapping at ROWID 1 and added
the second at ROWID 2. Both original jobs drained with exit zero and
the workers recorded the shutdown signal and start of flushing. The
shipping worker has no independent flush-completion message.

On ARM64 the first worker (PID 2268) completed the upload and live
backup. The original upgrade test refused to click because its test of
the Quit item's screen point and popup ownership failed. Its error
does not identify which condition failed. The observer reaped its own
process. This run ended before restoring the database or starting
a second worker. Both MSIs uninstalled successfully and both synthetic
profiles were removed. Detached replay at the measured commit confirmed
the x64 full result and the ARM64 live-only result.

| Original archive | ZIP SHA-256 | Returned SQLite SHA-256 |
| --- | --- | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45897825745/artifacts/15155041349) | `51fe553ac73d0dd7e0e7bb84a0b8b635d75052b851b85ee1966cd5a86b9d717e` | `c0e4061210df6af078b560f6a0d6ed1efd61817a20145b386abc88e19536f39a` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45897825745/artifacts/15154303301) | `6c487bf78164eae1afdbf3e686b0299083b5a29f39da80d5805ddba292dbafbe` | `60721a7f047b30d4801168e14ae6aa48b76fabe5e0e80394e569c6854d018ee4` |

## Installed Windows worker restart at f8cf6b1

A second Windows x64 run completed both installed uploads and opened
Rust's live backup in a fresh WPF process. At each Quit the observer
verified the original WPF client at physical point (751, 551) and the
unmodified upgrade fixture selected the highlighted Quit item. Detached
replay checked the original observer sources, native processes, peer
requests, restored database and both removals.

On Windows ARM64 the original WPF worker again uploaded the first PNG
and Rust returned its live backup. At Quit the WPF client extended from
(-20, 11) to (1008, 732). Its test point (751, 551) belonged to the
foreground window of another process. No menu opened and the observer
issued no cursor movement or click. The ARM64 replay passed through
backup and failed full restart. Both installations and synthetic profiles
were removed. The next observer launches its helper without a console
window and checks other points inside the same original client for a
verified WPF hit.

| Original archive | ZIP SHA-256 | Returned SQLite SHA-256 |
| --- | --- | --- |
| [Windows x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45899285120/artifacts/15155246528) | `1f141434ef85ed4ecd8e7230c1e05be9cfb6ca4c8e2fdd0a4392efc4c70b0ed2` | `dde53977b7bc2d3fa89b977806bbed915137acaccf10b65a2a8254935fcfc1c3` |
| [Windows ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45899285120/artifacts/15155800388) | `413ca579ac3a65947f9e17887710c4306e45ef888fbb21ea70281b27ce1292dd` | `354c2d39c7cfc6d3fa2cbfc2b7792283cd1515a05a165b1858af6d03615d99f2` |

## Installed Windows worker restart at d7c084c

On the hosted x64 desktop both WPF processes again uploaded the expected
PNG. The first returned mapping kept ROWID 1, and the new mapping used
ROWID 2. The worker and its replacement each exited via the original
highlighted Quit command. Both WPF windows owned the very first
observed menu point. The detached live and full comparisons passed.

On the original ARM64 input desktop, all 16 points sampled across the
installed client's rectangle belonged to the same foreground window
(HWND 66052, PID 9008, UI thread 1904). The WPF worker (PID 2600) had
already uploaded its first PNG. Rust returned the live backup from 16 WAL
frames. The observer moved no cursor, opened no popup and issued no
click. The independent live check passed and the full comparison failed
before restore. Both runners removed the original MSI and synthetic
profile. The original desktop's owner and geometry receipts are included
in each archive.

| Windows host | Original ZIP SHA-256 | Returned SQLite SHA-256 |
| --- | --- | --- |
| [x64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45900725198/artifacts/15155363507) | `4162fe0a585b303fc4d54d139ffde71df2d28efa772fb19f57793beae46afd53` | `cc3e244a8f8de53c854b81b43e3fff996cb0cb94fd2f9c574964f371a078f3a2` |
| [ARM64](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45900725198/artifacts/15155657463) | `fca5778b100c5a7156f94af6622a96ab56e547d2388a2d26633fdb5247dad276` | `2205ef38b3a353b7e1d5ef5c7e8b77cdafb9987e4215104c2ba744976b99a990` |

## Installed Windows worker restart at c4d05b6

The installed 3.0.4 WPF worker resumed from a live Rust backup on the x64
Default desktop and on a private ARM64 input desktop. Three fresh runners
each uploaded `signed-worker.png` to their own loopback peer and received
HTTP 201. The SQLite main file alone contained zero upload rows. Replaying
its 16 WAL frames reproduced the single committed row in Rust's standalone
return. Each original ZIP matched its GitHub Actions digest. Detached replay
at `c4d05b6929d9112de8b6e05f38ab99597782928b` verified the native build
and evaluated the live-backup and full-restart checks separately.

| Original archive | Live backup / full restart | WPF PIDs in launch order | ZIP SHA-256 | Returned SQLite SHA-256 |
| --- | --- | --- | --- | --- |
| [x64 Default](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45902841251/artifacts/15156648938) | Passed / passed | 664 → 848 | `b8acb104c96914286c5670a34795034618a92710a20cd19cc0f6422bc43927b5` | `a62f1ae020b3fe87133b3291fad4951089cd634b4d9ecb4e81b2d6a30ed735ad` |
| [ARM64 Default](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45902841251/artifacts/15156752398) | Passed / failed before restart | 3292 | `04f1a68f231d3d1c10f53b759132a73345bf3ce4a1a47c71b64e3d0c97c95512` | `f1b69d3b3f867709e904183b90db9ab5543602573a594a39b43acf59f8bd9a68` |
| [ARM64 private input](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45902841251/artifacts/15156941151) | Passed / passed | 3664 → 1092 | `8508621a85b18793ec767d555c4c4d71a2495b113466da2976bbc8866bbbe433` | `521167dd9f8c772d4b0719d69ffbded6b1f23b5135a4122e83e883328d0f1cd0` |

On both completed restarts, the second installed process opened the
returned database, kept the first asset at ROWID 1 and uploaded only
`after-restore.png`. Its HTTP 201 response matched the new asset at
ROWID 2. In each lifetime the first tested point belonged to the original
WPF client. Selecting the highlighted Quit command (ID 3) produced exit 0
and an empty WPF job. The logs recorded the shutdown signal and the
start of flushing. Flush completion remains unobserved.

In ARM64 console session 2, supervisor PID 1952 retained the original
`WinSta0\Default` handle and switched input to the newly created
`IfwQa_f1ec01be36014552bd0496fb450588a5` desktop. Observer PID 908
recorded the original WPF windows (HWNDs 131554 and 327926) and the two
native Quit helpers (PIDs 9976 and 5352) on that desktop. After the second
Quit, the observer exited with code 0. The supervisor switched back to
the original unlocked Default desktop in session 2 and closed both
desktop handles. This trial exercised the installed worker and its
application menu. Ordinary Explorer tray and RDP behavior have separate
acceptance checks.

On the ARM64 Default desktop, the first worker completed its upload and
live backup. All 16 points across its client hit HWND 66050, owned by
PID 8348. The observer stopped before moving the cursor or opening the
menu, then reaped its own WPF process. Database replacement and the
second launch were never reached. All three runners uninstalled the MSI
and removed the synthetic profile and scratch directory.

After the WPF startup and desktop code was shared with the activation
trial at `972adc6`, independent replay of all three new archives gave
the same three outcomes. The x64 Default and ARM64 private workers
each uploaded both PNGs across the restore and preserved ROWIDs 1 and 2.
On ARM64 Default, the first worker committed the upload and all 16 Quit
points hit another window. All three MSI uninstalls passed.
[x64 Default](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45905250633/artifacts/15158022801) ·
[ARM64 private](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45905250633/artifacts/15158295634) ·
[ARM64 Default](https://github.com/VoltKraft/immich-folder-watch/actions/runs/45905250633/artifacts/15157364158).
