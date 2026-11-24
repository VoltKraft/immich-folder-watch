# C# path-key readback across ICU profiles

Use the shipping store through the development-only
[StorageReadback project](../storage/dotnet/StorageReadback.csproj). Build once
from the repository root with the SDK in `global.json`. Give the SDK a private
home and cache. All fixture and readback directory arguments must be absolute
paths below this checkout's `artifacts/rust`.

Generate a fixture with each writer environment on the same native OS and
architecture. One must uppercase U+019B to itself and the other to U+A7DC.
Each writer captures its full invariant uppercase table in the same .NET
process that produces the databases. The manifest gives its SHA-256, counts
and context-batch result. The reader captures its own full table and verifies
both writer files against the [independently derived profiles](../../../docs/rust/rw02-legacy.md#independently-reproduced-casing-profiles).
The following example uses Linux x64. It assumes
the original three ICU 74.2 shared libraries and their versioned links are
available in the private directory named by `IFW_TEST_ICU74`, the default
.NET environment uses the newer casing table and the project's existing
NuGet cache contains the restored packages. [App-local ICU configuration](https://learn.microsoft.com/en-us/dotnet/core/extensions/globalization-icu#app-local-icu).

```bash
run="$PWD/artifacts/rust/casing-comparison"
export DOTNET_CLI_HOME="$run/sdk-home" DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_GENERATE_ASPNET_CERTIFICATE=false
export XDG_DATA_HOME="$run/sdk-data" XDG_CACHE_HOME="$run/sdk-cache"
export XDG_CONFIG_HOME="$run/sdk-config" NUGET_PACKAGES="$PWD/artifacts/nuget-packages"
mkdir -p "$DOTNET_CLI_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$run/empty-feed"
dotnet restore tools/rust-qa/storage/dotnet/StorageReadback.csproj \
  --artifacts-path "$run/build" --source "$run/empty-feed" \
  -p:EnableWindowsTargeting=false -p:NuGetAudit=false
dotnet build tools/rust-qa/storage/dotnet/StorageReadback.csproj -c Release \
  --artifacts-path "$run/build" -p:EnableWindowsTargeting=false --no-restore
fixture="$run/build/bin/StorageReadback/release/StorageReadback.dll"
older_icu=(env "LD_LIBRARY_PATH=$IFW_TEST_ICU74" DOTNET_SYSTEM_GLOBALIZATION_APPLOCALICU=74.2)
"${older_icu[@]}" dotnet "$fixture" --casing-fixtures "$run/writer-019b"
dotnet "$fixture" --casing-fixtures "$run/writer-a7dc"
"${older_icu[@]}" dotnet "$fixture" --casing-readback \
  "$run/writer-019b" "$run/writer-a7dc" "$run/reader-019b"
dotnet "$fixture" --casing-readback \
  "$run/writer-019b" "$run/writer-a7dc" "$run/reader-a7dc"
```

Each readback opens its own copies of the sensitive and insensitive databases
from both writers. It verifies the writer's byte digests, the native target,
the pinned shipping source and the complete logical contents of all four
tables. `result.json` records the actual reader casing, entries, repairs,
tombstone, exact album IDs, transfer times and the before/after hashes.
Verify that the two reports show different reader mappings and four passing
observations each, with `writerTablesVerified` equal to `true`. The readback
rechecks both original directories before publishing its report. Reuse
requires a new output directory. An unfamiliar reader retains its captured
TSV and a failing report with `readerTableVerified` equal to `false`. It
performs zero database lookups.

For a historical writer that predates in-process table capture, append
`--archived-writer-hashes <019b-manifest-sha256> <a7dc-manifest-sha256>`
to the readback command. Take the two manifest digests from the trusted
original receipt. The diagnostic result identifies each missing writer table
and records `writerTablesVerified` as `false`. Its reader table is present.

## Insert new identities on finalized copies

The [Linux x64 study](new-entry/run.py) reads the historical receipt and its
two finalized writer directories from `artifacts/rust/casing-profile-verified-f538495`.
Use the repository cache containing SDK 10.0.401, runtime 10.0.12 and the
private ICU 74.2 libraries. The host ICU must reproduce the qualified
Unicode 17.0 table. The driver needs a native Fedora x64 system with
Bubblewrap user, mount and network namespaces, GNU `ar` and Python with
zstd tar support. The output must be a fresh direct child of `artifacts/rust`.

```bash
python3 -B tools/rust-qa/legacy-keys/new-entry/run.py \
  --dotnet artifacts/flatpak-local-2.11.2/sdk/dotnet \
  --icu74 artifacts/rust/casing-oracle-verified-e59a691/icu74 \
  --output artifacts/rust/new-entry-comparison
```

The driver opens each donor directory relative to a held Linux directory
descriptor. It reads regular single-link inputs from their opened handles,
checks the attested receipt and mounts those exact bytes read-only. It
also mounts the five study files read-only and reconstructs the first-party
sources from a single Git revision. The native processes see a new root
containing the required system files, checkout inputs and private temporary
directories. The run records its separate network namespace, loopback
interface and empty IPv4 route table. The original package caches are read-only. Cargo uses its own
registry copy. Each C# invocation gets a read-only mount of the eight Rust
cases and a separate writable directory for its shipping store.

The same run authenticates the Rust distribution in
`artifacts/rust/toolchain-inputs`, the SDK tarball at
`artifacts/flatpak-local-2.11.2/dotnet-sdk.tar.gz`, and
`libicu74_74.2-1ubuntu3.1_amd64.deb` in
`artifacts/rust/portal-noble/development-01/packages`. It compares the host, SDK driver,
CoreLib and CoreCLR bytes with the .NET archive and the three ICU 74.2
libraries with the Ubuntu package. Cargo metadata, the locked target graph,
the original crate archives, the full unpacked sources and the selected
notices are checked with the storage assessment's verifier.

The development Rust writer builds against the storage assessment's locked
libraries. On separate copies it uses each explicit casing table to insert
three new entries in one transaction. It exercises a stable key, a changing
relative name and a changing source name. Each native C# reader captures its
complete casing table and calls the shipping store on fresh copies. The
[SQL verifier](new-entry/verify.py) compares the single-file results, ordered
source listings, account history, schema and every row with the original
inputs and the three expected inserts. The output retains the Rust receipts,
both C# reports and full tables, the copies, the five study sources, the
Git source archive and the verified crate archives. `evidence.tar` is the
raw export from the private namespace. `result.json` binds its digest
to the original directory and file identities checked before and after
the run.
