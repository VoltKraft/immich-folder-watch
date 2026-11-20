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
