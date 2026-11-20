# RW-01 native reference execution and Windows corpus review

Review date: **2026-11-20**. The executed reference run is
[43634286661, attempt 1](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43634286661),
started on **2026-11-14** at source
`3ca5b0a89d266e61e219239f84d896dc71528ba0` on `rewrite/rust`.
All four hosted jobs completed successfully. This record reviews that fixed run;
it does not imply execution of a later workflow or changes made after that source.

## Executed results

| Native lane | Hosted runner | Oracle export / independent verify | Portable reference TRX |
| --- | --- | --- | --- |
| Linux x64 | `ubuntu-24.04` | 29 fixtures, 215 assertions each; committed Linux golden also verified | 566 passed, 0 failed, 0 skipped |
| Linux ARM64 | `ubuntu-24.04-arm` | 29 fixtures, 215 assertions each; committed Linux golden also verified | 566 passed, 0 failed, 0 skipped |
| Windows x64 | `windows-2025` | 29 fixtures, 215 assertions each | 557 passed, 0 failed, 9 skipped |
| Windows ARM64 | `windows-11-arm` | 29 fixtures, 215 assertions each | 557 passed, 0 failed, 9 skipped |

The logs identify SDK **10.0.401**, with the oracle actually executing on
**.NET 10.0.15** in all four lanes. Its process and OS architecture assertions
passed as x64/x64 or ARM64/ARM64, respectively. This is native execution, not a
cross-build claim. The initial local Linux export used runtime 10.0.12; both hosted
Linux outputs still match that committed corpus byte-for-byte.

The Windows TRX files contain 566 results each: 557 `Passed` and nine `NotExecuted`.
Use the per-result outcomes as well as counters: their `notExecuted` counter is
zero despite those nine result records. Both Windows jobs skip the same tests:

- Eight `DBusBackgroundPortalRequestTests` cases: early-response/legacy handle,
  supported options/signal wait, timeout, caller cancellation, method errors,
  unrelated signals/cancelled response, existing-connection cancellation, and
  stalled-session disposal. Each explicitly requires Linux and an isolated
  `dbus-daemon`.
- `FolderWatchWorkerPersistenceTests.Sync_WriteDeniedDirectorySkipsDownloadsAndRecoversWithoutRestart`,
  which explicitly requires unprivileged Unix file-mode enforcement.

All nine exact test names have `Passed` results on **both** Linux architectures.
The Windows skips are retained in the evidence; they are not Windows passes.

## Artifact provenance and integrity

The four ZIP archives were downloaded from the exact run's GitHub Actions artifact
API. Each local SHA-256 equals the artifact API's advertised `digest`; byte sizes
also match. There were no expired artifacts when retrieved.

| Lane / artifact ID | ZIP bytes | Verified ZIP SHA-256 |
| --- | ---: | --- |
| Linux x64 / `14129800744` | 161303 | `762a1c7ea163fa0e6a6728910c62e011ac7c98e2a525a7b5b64a4ab1dff4661d` |
| Linux ARM64 / `14129960158` | 161622 | `2641dcfb174134f070b05af3bb68ac398927cbf64bfc217d6fa21e1002898ffb` |
| Windows x64 / `14129690524` | 162743 | `99be5fc93f15eea28c387fe5f75df4e501365c7bdd14927093724e57f44c3f8f` |
| Windows ARM64 / `14129237006` | 162952 | `d94c861517c3dcbea8d12fd7f059d1d485d3dd80e1053e68358dc3fb6c50badc` |

Before extraction, every archive was checked for duplicate members, absolute or
traversing paths, backslash/drive-name ambiguity, symbolic links, encrypted entries,
unexpected extensions and excessive expanded size. Each contains exactly 30 regular
files: 29 fixtures under its expected `oracle/linux/` or `oracle/windows/` prefix
and `test-results/core-reference.trx`. ZIP CRC checks passed. No executable artifact
was run during this review.

The ignored local evidence directory is
`artifacts/rust/hosted-reference/43634286661/`: original ZIPs, extracted files, job
logs and JSON verification reports. The fixture manifests verify all 28 payload
hashes and identify ten owning source hashes. There are no personal profiles,
media or production credentials in the imported fixture set.

Both Linux corpora are byte-identical to each other and to the committed
[Linux golden](../../rust/tests/fixtures/legacy/linux/manifest.json). Both Windows
corpora are byte-identical to each other. The reviewed
[Windows golden](../../rust/tests/fixtures/legacy/windows/manifest.json) was copied
unchanged from artifact `14129690524`; its manifest SHA-256 is
`dde93d2a00efe55541e631bfe480e27c3226772f6a642bd58832c10b70f9c5f9`.
No generated content or source hashes were manually normalized or rewritten.

## Reviewed platform differences

Exactly eleven of the 29 corpus paths differ between Linux and Windows:
five configuration expectation files, the manifest, the two SQLite expectation
files, two SQLite SQL snapshots and the native path-vector file.

The substantive differences are expected native **path semantics**:

- Runtime profile-relative paths use `/` on Linux and `\` on Windows.
  `C:\Pictures\2024` is absolute on Windows but a relative filename containing
  backslashes on Linux. Editable configuration and serialized YAML match.
- Windows vectors exercise drive roots, UNC share roots and alternate separators;
  Linux vectors exercise Unix roots and literal backslashes. Trailing-root and
  dot-segment source normalization follows the native `Path` APIs. Relative dot
  components are retained by the store; these keys do not confer filesystem access.
- Stored source paths/keys, relative paths/keys and corresponding repair-journal
  paths reflect those native rules. Case-insensitive vectors retain the .NET
  invariant-uppercase behavior, including sharp-S rather than expanding it to `SS`.

Account hashes, invariant-uppercase vectors, YAML inputs/writer output, timestamp
encodings, enum values, tombstone boundaries, ownership outcomes, history/backfill,
repair conflict observations and WAL-backup observations match across platforms.
The future-version WAL mutation is also observed on both platforms and remains a
[stronger Rust requirement](rw01-storage-contract.md#baseline-discrepancy-that-rust-must-improve).

The remaining difference is **checkout representation**, not changed SQL behavior:
all ten Windows source hashes match the committed LF blobs transformed to CRLF.
Linux source hashes match the raw LF blobs. C# raw multiline strings preserve
those source line endings, so Windows SQLite schema JSON includes escaped `\r\n`
where Linux includes escaped `\n`. Exported fixture files themselves are UTF-8/LF
on both platforms; the SQL export normalizes its physical line endings.

## Checkout contract for subsequent verification

A local read-only Git filter check against the fixed source reproduced the
observed source hashes:

| `core.autocrlf` applied by Git's checkout filters | Windows source hashes matching |
| --- | ---: |
| `true` | 10 of 10 |
| `false` | 0 of 10 |
| `input` | 0 of 10 |

`false` and `input` preserve LF on checkout. Their Windows builds would produce
different source hashes and raw-schema line endings from this reviewed Windows
baseline even though the application SQL semantics are equivalent. The hosted run
did not print its `core.autocrlf` setting; the CRLF byte correspondence above is
observed evidence, and the setting correspondence is reproduced with Git filters.

The follow-up workflow change pins the reference checkout's source representation
explicitly: LF for Linux, CRLF for Windows. Its accompanying `.gitattributes` rule
sets `rust/tests/fixtures/legacy/** text eol=lf`, so an ordinary
Windows checkout does not turn the generated golden files into CRLF and fail the
oracle's exact-content comparison. Local Git-filter checks with the new rule
preserve all 28 committed Linux payload hashes under `true`, `false` and `input`;
the same path rule covers the imported Windows files. These filter checks are
not a new native Windows execution. A future deliberate move to canonical LF
source hashing/schema normalization must regenerate and review both native
corpora rather than editing manifests by hand.

The follow-up workflow also adds reviewed Windows-golden comparison to both
Windows lanes. The original run verified Windows export against a fresh regeneration,
but it could not compare a checked-in Windows golden that did not yet exist.
Passing that follow-up workflow is separate evidence from this archived run.

## Acceptance boundary

This supplies four-target native **C# reference** execution and reviewed
configuration/SQLite compatibility fixtures for RW-01. It does not establish
Rust codec compatibility, native Rust GUI/tray/portal behavior, accessibility,
renderer fallback, installed-package migration or rollback after real synthetic
sync activity. UNC entries here are path-string tests, not access to a UNC share.
Those required gates remain in [the acceptance record](acceptance.md) and
[the storage contract](rw01-storage-contract.md).
