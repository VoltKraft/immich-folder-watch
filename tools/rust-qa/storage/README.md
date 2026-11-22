# Native synthetic storage assessment

This is a development-only Cargo workspace for RW-02. It is separate from
`rust/Cargo.toml`; its dependencies are not application dependencies. It reads
only the reviewed synthetic RW-01 corpus and creates fresh databases below
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
