# Bounded native storage faults

This RW-02 development-only workspace tests the existing reviewed SQLite
assessment with real process termination and SQLite capacity failure. It does
not implement a production adapter or start RW-03. It adds no external package,
feature or native source to the [reviewed storage graph](../storage/README.md).
See [scope, results and limits](../../../docs/rust/rw02-storage-faults.md).

From the repository root, with the pinned native Cargo/Rust compiler on `PATH`,
a populated reviewed Cargo cache, the selected .NET SDK and native C compiler:

```sh
python3 tools/rust-qa/storage-faults/run.py x86_64-unknown-linux-gnu \
  --output artifacts/rust/storage-faults/linux-x64-new \
  --cargo-home artifacts/rust/storage-assessment/cargo-home \
  --dotnet artifacts/flatpak-local-2.11.2/sdk/dotnet --tmpfs
```

The six portable cases run first, in both casing modes. The native volume
cases follow, so their availability cannot suppress the portable observations.

The target must be native. The interface also supports
`aarch64-unknown-linux-gnu`, `x86_64-pc-windows-msvc` and
`aarch64-pc-windows-msvc`; those lanes require their own execution evidence.
Use their installed `dotnet` command or repository-local SDK path. MSVC is
required on Windows. Omit `--tmpfs` outside Linux or for the six portable cases.
No external service or installation is needed. The optional Linux ENOSPC check
requires existing Bubblewrap and permission to create a private user/mount/network
namespace. Its tmpfs is capped at exactly 8 MiB and exists only in that namespace.
The runner kills only children it starts. Compilation uses `--frozen`; cached
NuGet restore disables advisory retrieval explicitly, and does not establish a
current vulnerability scan. On Linux the .NET processes use a private home and
XDG directories below the run's `build/dotnet-cli/`. Set `NUGET_PACKAGES`
to the populated fixture package cache for an offline restore.

On a **disposable GitHub-hosted Windows candidate** for this repository's
`rewrite/rust` branch, select `--windows-vhd` instead of `--tmpfs`:

```powershell
python tools/rust-qa/storage-faults/run.py x86_64-pc-windows-msvc `
  --output artifacts/rust/storage-faults/windows-x64-new --windows-vhd --dotnet dotnet
```

Use `aarch64-pc-windows-msvc` and a fresh ARM64 output for the other native target.
The runner requires native Python/Rust/.NET architecture, hosted-runner identity
and available Windows virtual-disk/admin capability. Missing capability records
`unavailable` and exits nonzero; it never becomes a passing filesystem-full test.
There is no automatic privilege/policy change or alternative host disk selection.
Do not run the Windows volume experiment on a personal or persistent machine.

The source-pinned [empty image recipe and notice](windows-image/NOTICE.md) produce
a 15-MiB FAT16 data partition in a fixed 16-MiB VHD. Windows needs only Python
stdlib and its installed `virtdisk.dll`/`kernel32.dll`, loaded from System32.
It verifies the whole initialized file before attachment, retains its file
identity without delete sharing, and attaches only its own virtual handle with
`NO_DRIVE_LETTER` and non-permanent lifetime. It verifies the handle-derived
physical disk's exact MBR and size, then accepts only a new volume GUID with one
matching disk extent, filesystem serial, label and cluster geometry. No attached
disk is formatted, initialized, brought online or selected by ambient number.
No drive letter or directory-mount fallback exists. The fixed backing is created
only with at least 256 MiB free on the local host filesystem.

Only that new volume GUID is passed to the native worker, together with the
supervisor's fresh authorization marker. The native filler must observe Win32
39 or 112; the supervisor must independently observe zero available/free bytes
while SQLite returns 13. It then permits removal of only the owned filler and
the same-volume backup restore. This private pipe sends exactly the 14 UTF-8
bytes `release-space\n`, with LF translation disabled even on Windows. The
worker retains its exact-token check; no trimming or broader acknowledgement is
accepted. The supervisor records the sent bytes only after write and flush.
Both modes use the existing Rust/C# recovery,
producer-hash and byte-corruption controls: eight cases and 208 C# assertions
when the native Windows qualification passes. An ordinary synthetic file also
records extended and legacy IDs on one handle before/after rename; a cached FAT
ID never selects a destructive action.

Every exit path closes owned handles, attempts explicit detach and retains a
cleanup receipt. Success additionally requires the volume to disappear, fixed
MBR/footer and size to remain unchanged, and a hash of the detached VHD. The
initialized and final images are synthetic evidence, not recovery backups or
product assets. Source-bound native results are recorded in the linked evidence
document; the optional provider follow-up below needs its own native result.

After independent review and a passing native recovery qualification, the
**separate opt-in** `--windows-provider` can observe the unchanged workspace
`safe-fs` API on the same final, insensitive VHD. It never creates another VHD.
The default command above remains without a directory mount.

```powershell
python tools/rust-qa/storage-faults/run.py x86_64-pc-windows-msvc `
  --output artifacts/rust/storage-faults/windows-x64-provider-new `
  --windows-vhd --windows-provider --dotnet dotnet
```

Use the ARM64 target and a new output for its separate native result. This option
requires the existing hosted Windows gates, a mount right and a local fixed NTFS
`RUNNER_TEMP` outside the checkout. Its path and the workspace must be disjoint.
The supervisor creates one new, private, empty directory there and holds its
NTFS identity. This places even a retained mapping outside the evidence
collector and the workflow upload. Missing capability is reported as
`unavailable`. A change to the already authenticated VHD is a failure.

The last VHD stays attached while all eight existing Rust/C# recovery cases,
208 C# assertions, corrupt-copy controls and original-snapshot comparisons finish.
The supervisor writes, fsyncs and closes `recovery-before-provider.json` before
it reads the optional sources, imports the provider, runs Rustfmt and the
portable controls, builds the Rust probe or verifies its native PE machine.
The default recovery source archive includes the workspace manifest inherited
by `ifw-legacy`. Optional source copies, hashes and command logs live under
`provider-preparation/`. Final VHD detach and readback are pending at the
checkpoint. Only the new NTFS directory is associated with the authenticated
volume GUID. The child receives an ordinary FAT subdirectory beneath it.

A direct native Rust child opens and reads one fixed 45-byte synthetic file,
performs an ordinary fixture rename, reads the held lease and reopens the new
name through `safe-fs`. Its old-name match must be false and its new-name match
true. The supervisor then revalidates the VHD and reads the names and bytes
through its independent volume-GUID path. It requires exactly `renamed.txt`
with the original length and contents and records the observed SHA-256.
File-identity equality across the rename is recorded. No
timestamp write, replacement, attack simulation, production rename API or cached
identity cleanup is exercised. The child has a 15-second deadline and a
10-second termination wait; the supervisor waits before deleting owned names.

The supervisor removes only the names it created, undoes only its authenticated
mount mapping, checks the empty NTFS stub's identity before removal and requires
no remaining volume mount path. All pre-existing volume file hashes and measured
capacity must match after cleanup. A provider import, build, observation or
receipt-write failure still reaches the final VHD snapshot check, detach,
detached-image readback and all eight deferred original snapshot checks.
An unconfirmed child exit prevents name removal and is retained as an explicit
cleanup failure.

`windows-provider.json` and `result.json.provider_followup` record this outcome
separately from `result.json.status`, which retains the storage result. With the
option selected, `selected_checks_status` also controls exit status: 0 only when
both passed, 2 for an unavailable provider, otherwise 1. The unchanged `safe-fs`
sources, workspace/crate manifests and probe source are exported with hashes;
the pinned native compiler builds an isolated rlib and executable, records their
hashes and checks the executable's PE machine. No Cargo dependency or lockfile
changes. Portable controls run with
`python tools/rust-qa/storage-faults/test_windows_provider.py -v`; test doubles
and the local Linux compile do not establish a Windows FAT provider pass.

Portable image/layout, corruption, capability-gate and simulated cleanup checks:
`python tools/rust-qa/storage-faults/test_windows_image.py -v`. These checks do not
execute or substitute for Windows mounting or filesystem exhaustion.
Crash-capture and unchanged-byte negative controls run with
`python tools/rust-qa/storage-faults/test_crash_capture.py -v`. Its actual mandatory
byte-lock check runs only on Windows and is explicitly skipped elsewhere. Both
test commands are included in the maintained runner.
Source-export controls run with
`python tools/rust-qa/storage-faults/test_source_snapshot.py -v`; the maintained
runner also executes them, including a transfer that excludes hidden paths.

Output must be a fresh directory strictly below `artifacts/rust/storage-faults`.
Each failed run is retained; retry with a new name. Only this fresh synthetic tree
is mutated. No user application profile is opened. Each ordinary command step
(including builds, the portable page-limit worker, Rust verification and C#
readback) has a 600-second timeout. The supervised crash worker has a 30-second
readiness deadline and a 10-second termination wait. The private tmpfs supervisor
has a separate 30-second watchdog and a 10-second child termination wait.
Windows volume discovery is bounded to 30 seconds, its native worker to 60
seconds, termination to 10 seconds and detach readback to 10 seconds. The transaction
payload is fixed at 2 MiB. The `SQLITE_FULL` case limits database growth to 16
pages beyond its measured initial size; this is not filesystem `ENOSPC`.

The original `storage/src/main.rs` compiles unchanged as a separate seed binary.
The fault binary also compiles an exact byte-for-byte copy of that source with
only two appended test-visibility wrappers for its snapshot helper and ordinary
existing-profile opener. The worker closes the seed and backup connections
before that opener checks the restored schema in private scratch and opens the
writable database. It establishes the WAL baseline before the fault transaction.
`build.rs` tracks the seed entry point and both sibling modules,
`preflight.rs` and `wal_preflight_cases.rs`. It copies both modules unchanged
beside the generated fault entry point. The runner compares each compiled copy
with the archived first-party sources and retains the three files under
`generated-source/` for each build profile. The new fault transactions and kill
barriers are test code. Cargo.lock is generated, and all external identities and
features must equal the existing 31-package reviewed closure before compilation.

The six scenarios cover both C# casing modes:

1. Commit a four-table change and take a consistent snapshot with the SQLite
   backup API while committed pages are still exclusively in WAL. Close the
   completed backup, emit its SHA-256 before any verifier reopens it, then verify
   the full content and emit the transaction confirmation with that same digest.
2. For crash-before-commit, change all four tables, spill dirty pages to WAL, and
   block. The parent kills the child with SIGKILL/TerminateProcess; no Rust
   transaction destructor executes. A new process must see only confirmed data.
3. For commit-before-ack, commit the second transaction and block before emitting
   its application acknowledgement. The test barrier discloses the commit to the
   harness. Recovery must find the complete committed transaction; an absent
   application acknowledgement does not imply an absent commit.
4. For `SQLITE_FULL`, apply three updates and attempt the large fourth update at
   the measured page limit. Require exact SQLite error 13, record autocommit and
   dirty transaction state, then drop the transaction and require complete rollback.
5. Reopen each failed database in a new Rust process, run full `integrity_check`
   and compare the entire schema/version/four-table snapshot. Restore the retained
   pre-fault snapshot through the backup API into a new file. Verify all content
   plus a write-and-rollback operation. A separate backup clone receives a real
   SQL update to its album ID and must fail the expected snapshot comparison.
6. With `--tmpfs`, both casing modes additionally consume all space in an actual
   private 8-MiB tmpfs. A bounded filler must return OS errno 28; an independent
   `statvfs` measurement must report zero free/available bytes while SQLite returns
   error 13. The normal SQLite page limit remains large. Release only the owned
   filler, restore the pre-fault snapshot via the backup API on the same tmpfs,
   and retain that result before the namespace exits. Readonly fixture binds are
   copied privately with hash checks so WAL locking sidecars can be created.
7. The actual existing C# Core readers independently validate entries, repairs,
   history, exact album ownership, account separation, 64-bit values and tombstones
   in the recovered database, snapshot and restored database (also the tmpfs
   restoration, when present). The reader initializes databases and can rewrite
   header bookkeeping. Rust and C# each read their own disposable snapshot copy,
   authenticated against the native producer's digest before opening SQLite.
8. Carry that original digest through the raw process-kill and ENOSPC events.
   Check the actual retained file before and after each Rust/C# phase and again
   after all cases finish. The supplied CLI digest is always the early producer
   value, never a replacement measured by a later reader. In every case, flip
   one byte in another isolated copy. Both actual verifier entry points must
   return the specific hash-mismatch error before opening SQLite or producing
   derived files. The original and corrupted copy must both remain unchanged
   throughout those rejection trials.

The producer SHA-256 and its independently retained supervisor receipts establish
byte continuity within this isolated experiment. They are not a digital signature
or proof against an attacker who controls both the producer and supervisor.
Individual verifier commands require the original digest as their final argument:
`ifw-storage-faults verify <case> <producer-sha256>` and
`dotnet FaultReadback.dll <case> <producer-sha256>`.

Raw DB/WAL copies are mandatory before and after the kill and must match exactly.
Linux additionally captures and compares SHM when present. Windows captures SHM
only after termination, before any SQLite reopen: its active mandatory byte locks
deny ordinary reads. The receipt names every captured and compared file, records
the Windows omission and never claims a before/after SHM comparison on that host.
No DB/WAL copy denial, missing file or byte mismatch is ignored. These files are
forensic evidence, not recovery backups; the transient SHM index contains no
database content ([SQLite WAL format](https://sqlite.org/walformat.html)).
Recovery uses only the completed SQLite backup API snapshot. Actual
failures and all source/recipe/native compiler hashes, dependency archives,
notices, logs and per-case JSON remain in the output. The large build tree is
kept locally but excluded from the evidence-hash inventory; its actual executables
and generated source are separately hashed or archived. Do not upload build
caches as evidence. No remote side effect is undone by restoring a database.

The explicitly selected source inventory is exported byte-for-byte. Its existing
`first-party-source-hashes.json` retains original repository-relative logical
paths. `first-party-source-paths.json` maps every logical path to its stored path
relative to the run output. Ordinary sources keep their existing
`first-party-sources/<logical-path>` location. A logical path with any dot-prefixed
component instead uses `first-party-hidden-sources/<key>.source`, where `key` is
the lowercase SHA-256 of the UTF-8 logical path. The lookup table preserves that
exact original path; it is not a renamed source or altered notice. The export
checks each copied digest and refuses existing destinations. Both indices and
all stored bytes are covered by `evidence-hashes.json` and have visible paths.
This changes no upload setting and adds no uninventoried source or hidden file.
For older exports without the new lookup table, the stored location is the
previous `first-party-sources/<logical-path>` convention. Missing bytes in an
older hosted artifact must still be reported separately; a Git reconstruction
does not retroactively make them present in that artifact.

## Local Windows x64 VHD trials

Use an elevated PowerShell in the disposable Server 2025 VM with the pinned
native toolchain, MSVC, .NET SDK and offline Cargo inputs. From the checkout
root, run the same recovery and provider cases as the ARM64 runner.

```powershell
python -B tools/rust-qa/storage-faults/run.py x86_64-pc-windows-msvc --local-qa-vm --windows-vhd --windows-provider --cargo-home artifacts/rust/storage-cargo-home --output artifacts/rust/storage-faults/local-x64
```

Choose a fresh output directory per run. Each filesystem-full case records
the host type alongside the original VHD, its native attachment and cleanup.
