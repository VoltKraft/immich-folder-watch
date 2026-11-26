# Native synthetic storage assessment

This is a development-only Cargo workspace for RW-02. It is separate from
`rust/Cargo.toml`; its dependencies are not application dependencies. It reads
the reviewed synthetic RW-01 corpus and creates fresh databases below
`artifacts/rust`. The C# tool calls existing Core readers after Rust writes and
backs up those databases. It never opens an installed application profile.

Use Python 3.11 or newer, the repository's pinned native Rust compiler and .NET
SDK, and a native C compiler (MSVC on Windows). From the repository root:

```text
python3 tools/rust-qa/storage/run.py x86_64-unknown-linux-gnu --output artifacts/rust/storage-native/linux-x64
```

Replace the target with one of `aarch64-unknown-linux-gnu`,
`x86_64-pc-windows-msvc` or `aarch64-pc-windows-msvc` on its actual native host.
`--output` must not exist; omit it to use a fresh timestamped directory. Optional
`--cargo-home` and `--dotnet` select repository-local installations.
`--offline` requires cached dependencies and disables NuGet advisory retrieval
for that run. It is not evidence of a current advisory scan.

The runner verifies the exact lockfile, 31 original crate archives, all unpacked
source bytes, 62 supplied notice files, four native SQLite inputs, native feature
graph and native corpus hashes before compilation. It pins bundled SQLite and
disables native extension loading, then checks actual runtime compile options and
the SQLite source ID. MSVC must honor the same `-U`/`-D` options; a missing option
fails the runtime gate. Native compiler commands are retained in build logs.
All build-flag overrides removed from the subprocess environment are recorded by
name, without dumping the parent environment.

Select `--stored-keys` to write two more synthetic C# backups and exercise
read-only identity lookup with the two independently qualified casing tables.
The driver checks all four logical tables against C# output and keeps
derived controls in their own directory. The completed report is
`stored-keys/result.json`. The two-generation Fedora experiment also covers
cross-library reads with the same C# runtime.
[Stored SQLite identity results](../../../docs/rust/rw02-legacy.md#stored-sqlite-identities-across-two-casing-profiles).

On fresh copies of those two backups, Rust attempts a key on which the
qualified tables agree. The native C# store reads and updates the new row
twice. In insensitive mode the test also refuses a key on which the tables
disagree and checks the original database hash. The top-level `result.json`
records the row and counts under `storedKeys.newEntries`. Each standalone
database is available under `native-insert-*`.

### Restore after a synthetic download

`--worker-activity` adds the shipping worker to the same native SQLite
assessment. Run from a clean committed checkout with both SDKs on PATH.

```sh
python3 -B tools/rust-qa/storage/run.py x86_64-unknown-linux-gnu --worker-activity \
  --output artifacts/rust/worker-backup-native/linux-x64
```

The first worker downloads `photo.jpg`, records its mapping and account Last
Sync, and stops. Its private watch directory remains alive. Rust inspects
both finalized backups. It must reject the earlier backup before creating
an output. It uses SQLite's backup API on the later one and rereads all
four tables. The second worker receives those exact returned bytes in a
disposable copy and reconciles the original watch directory. Its
xUnit output identifies both the JSON observations and the backup it consumed.
The default C# reference continues to run its own restore on all four targets.

### Restore after a synthetic upload

The same command runs a second exchange in a fresh profile. The shipping
worker uploads eight bytes to a synthetic peer, which stores its own copy
and derives the asset ID from the received bytes. Rust refuses the earlier
database and uses SQLite's online backup API on the post-upload mapping and
account history. The second worker opens that returned backup and reconciles
the same files. The peer records every unexpected download, membership change,
album mutation and trash request through worker shutdown.

### Backup helper for the installed Flatpak

On native Linux x64 or ARM64, add `--installed-upload-backup --offline` to
the storage assessment command to retain the release executable
`installed_upload_backup` and its SHA-256 in `result.json`. The
[installed handover fixture](../../RustCompatibilityOracle/installed/interop/installed_backup.py)
uses it inside the isolated Flatpak desktop with the synthetic upload
configuration, original loopback peer and the signed worker's live SQLite
store. The helper opens that store read-only, checks the committed upload
and account history, and creates the bounded backup at
`/qa/installed-returned.db`. The installed handover records the subsequent
worker restart separately from the build.

### Restore after a deletion or interrupted repair

The other two exchanges use the same shipping worker. For deletion, the
first worker removes the exact remote asset from its album. Rust accepts
the backup containing the tombstone. The restarted worker reconciles the
empty album and the peer retains the same nine bytes in trash. For repair,
Rust accepts the backup with the pending journal entry, after the file's
timestamp has already changed. The restarted worker completes the repair
with the original transfer and account history. Each case has its own
directory, peer or watch root and xUnit result.

To replay one exchange on another host, retain its directory from the
native archive. Pass the original target triple and full commit ID. The
reader checks the SQLite state, media and xUnit execution. The deletion
and repair directories also contain the compiled C# assemblies used by
their respective workers.

```sh
python3 -B tools/rust-qa/storage/worker_activity.py path/to/worker-activity TARGET FULL_COMMIT
python3 -B tools/rust-qa/storage/worker_activity.py path/to/worker-upload-activity TARGET FULL_COMMIT --upload
python3 -B tools/rust-qa/storage/worker_activity.py path/to/worker-deletion-activity TARGET FULL_COMMIT --kind deletion
python3 -B tools/rust-qa/storage/worker_activity.py path/to/worker-repair-activity TARGET FULL_COMMIT --kind repair
```

The parent `result.json` identifies the compiled Rust executable, C# test
assembly and original build inputs. The peer supplies synthetic Immich metadata
and bytes in process. Candidate installations and sync-engine rollback have
separate acceptance rows.
[Legacy case](../../../docs/rust/rw01-storage-contract.md#download-activity-and-the-latest-backup) · [Feasibility workflow](../../../.github/workflows/rust-feasibility.yaml).

Each output contains `result.json`, `evidence-hashes.json`, step logs, first-party
source copies, untouched `.crate` archives, supplied notices, feature graphs and
the original/backup synthetic databases with Rust and C# reports. Large build
products remain in a separate `artifacts/rust/storage-build/<run-id>` directory.
The runner archives failing output too; a directory's existence is not a pass.

`inputs.json` is generated review evidence, not an automatic approval mechanism.
`record-inputs.py --reviewed-source-inventory <reviewed-inventory.json>` regenerates
it only from a separately audited inventory and matching offline Cargo sources.
Changing dependencies, features, native flags, assets or notices requires a new
source review before regenerating it. Do not hand-edit Cargo.lock or inputs.json.

See [the storage audit](../../../docs/rust/rw02-storage-inputs.md) for license
disposition, measured behavior, original source evidence and outstanding cases.
YAML, production migration, existing future-schema WAL, full-disk/process-crash
recovery and cross-environment identity policy are outside this bounded proof.

### Read the frozen three-profile Fedora study

The separate developer diagnostic accepts the original three C# writer
receipts from `86ae038`. Their same-process casing exports cover ICU
Unicode 15.1, .NET 10.0.12 managed invariant casing and ICU Unicode 17.
The independent C# readers at `3c58fc1` exercised each writer in both path
modes. The diagnostic binds the writer's build, tables and snapshot to
those receipts. It uses the same immutable SQLite and historical lookup
implementation as the ordinary two-profile inspector.

Build the example with the [pinned native toolchain](../../../docs/development.md#rust-feasibility-workspace)
and the reviewed storage build flags, then pass the two retained evidence
directories and a fresh output directory below `artifacts/rust`.

```bash
export CARGO_HOME="$PWD/artifacts/rust/storage-assessment/cargo-home"
export CARGO_TARGET_DIR="$PWD/artifacts/rust/three-profile-inspector-build"
export LIBSQLITE3_SYS_USE_PKG_CONFIG=0
export LIBSQLITE3_FLAGS="-USQLITE_ENABLE_LOAD_EXTENSION -DSQLITE_OMIT_LOAD_EXTENSION"
cargo build --manifest-path tools/rust-qa/storage/Cargo.toml --frozen --release \
  --target x86_64-unknown-linux-gnu --example inspect_stored_keys
python3 -B tools/rust-qa/storage/study_stored_keys.py \
  --probe "$CARGO_TARGET_DIR/x86_64-unknown-linux-gnu/release/examples/inspect_stored_keys" \
  --writers artifacts/rust/managed-invariant-verified-86ae038 \
  --readers artifacts/rust/managed-readback-verified-3c58fc1 \
  --output artifacts/rust/stored-keys-three-profile
```

The observer explicitly selects `--three-profile-study`, rechecks the
original writer files and compares each returned key with the physical
SQLite rows using independent Unicode projections. A returned key preserves
the stored spelling. Absence, ambiguity and possible aliases are read-only
observations. Creating or rewriting identities requires a separate
application policy. [Study sources and Unicode License v3 notice](../legacy-invariant/README.md).

### Update the size of a historical entry on a new copy

The separate `update_study_copy` example copies an authenticated donor into a
fresh directory below `artifacts/rust/stored-key-mutations`. It resolves the
displayed paths with the shared historical lookup inside an immediate SQLite
transaction. An agreed, existing entry with the expected size of 19 bytes can
be changed to 37 bytes. The update binds the original physical account,
source and relative keys. The observer compares the complete before/after
schema and all four tables. It retains both databases and the request.

Use the same Cargo setup as above and build both examples with `--examples`.
Build the extended C# observation command in its private offline environment
using the [StoreIdentities build procedure](../legacy-invariant/README.md#reproduction-on-linux-x64).
Pass that assembly, the pinned .NET host and the qualified ICU 74.2
directory. The observer stages the original shipping Core DLL from the
frozen reader build and runs the two shipping store APIs on separate copies.

```bash
python3 -B tools/rust-qa/storage/study_file_sizes.py \
  --probe "$CARGO_TARGET_DIR/x86_64-unknown-linux-gnu/release/examples/update_study_copy" \
  --writers artifacts/rust/managed-invariant-verified-86ae038 \
  --readers artifacts/rust/managed-readback-verified-3c58fc1 \
  --dotnet "$(command -v dotnet)" --reader-dll "$run/build/bin/StoreIdentities/release/StoreIdentities.dll" \
  --older-icu "$IFW_TEST_ICU74" --output artifacts/rust/stored-key-mutations/file-sizes
```

The six updates cover both path modes for each writer. Nine refusal cases
cover ambiguous and possible aliases, unexplained stored keys, both absence
outcomes, stale expectations of both 20 and 37 bytes, a different account
and an unknown same-process table. Each successful update repeats the
operation against the actual target size of 37 and verifies its digest.
With umask zero the direct Rust process creates a 0700 case directory and
0600 database files. SQLite opens only the freshly created copy for writing.

The C# and Python readers require a finalized pair of single-link regular
files with rollback-journal headers. Both check the two names and contents
around copying or reading. On a separate copy, a committed WAL makes
38 bytes visible while the main file alone still shows 37. Both readers
must reject it as input. Other controls cover an isolated WAL-mode main
file, an extra directory entry, a symbolic link, a hard link and a FIFO.
The frozen donors contain entries and transfer history. Their repair
and ownership tables are empty. New identities, populated repair or album
changes and external synchronization need separate evidence.
