# C# path-key readback across ICU profiles

Use the shipping store through the development-only
[StorageReadback project](../storage/dotnet/StorageReadback.csproj). Build once
from the repository root with the SDK in `global.json`. Give the SDK a private
home and cache. All fixture and readback directory arguments must be absolute
paths below this checkout's `artifacts/rust`.

Generate a fixture with each writer environment on the same native OS and
architecture. One must uppercase U+019B to itself and the other to U+A7DC.
Keep each writer's [complete scalar export](../../../docs/rust/rw02-legacy.md#independently-reproduced-casing-profiles)
with its observed profile. The following example uses Linux x64. It assumes
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
observations each. The readback rechecks both original directories before
publishing its report. Reuse requires a new output directory.
