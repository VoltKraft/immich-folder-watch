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
was produced on native Linux x64. Native Windows output must be independently
generated, reviewed and retained. The case-insensitive mode on Linux exercises
the store's explicit casing switch; it does **not** emulate Windows path parsing,
UNC access, drive roots or Windows filesystem behavior. Four-target execution and
native Windows corpus review remain separate evidence in the main status record.

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
