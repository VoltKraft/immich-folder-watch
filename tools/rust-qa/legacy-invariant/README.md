# Managed invariant globalization in .NET 10.0.12

This development fixture reproduces the third uppercase table observed with
`DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` and measures its effect on synthetic
SQLite path keys. A table describes observable behavior. The writer installation
that produced an existing database can remain unknown. The storage migration
qualifier continues to accept its two independently reviewed ICU tables.

## Source reconstruction

The native CoreLib reports the version suffix
`95017c711e6afc1085133d440e42b4bd78155701`. The .NET 10.0.12 release's
source manifest maps that build to runtime commit
`4271d88e0aebf3d04f188f1334c2220d80555ef6`.
[Release source manifest](https://github.com/dotnet/dotnet/blob/95017c711e6afc1085133d440e42b4bd78155701/src/source-manifest.json).

The runtime generator selects Unicode 16.0 and suppresses casing offsets for
U+0130, U+0131 and U+017F. U+0130 already uppercases to itself. The other
two exclusions remove U+0131 → U+0049 and U+017F → U+0053 from Unicode's
1,477 simple uppercase changes. Managed invariant strings use the generated
casing data for both BMP characters and surrogate pairs.
[Generator project](https://github.com/dotnet/runtime/blob/4271d88e0aebf3d04f188f1334c2220d80555ef6/src/libraries/System.Private.CoreLib/Tools/GenUnicodeProp/GenUnicodeProp.csproj#L6),
[generator exclusions](https://github.com/dotnet/runtime/blob/4271d88e0aebf3d04f188f1334c2220d80555ef6/src/libraries/System.Private.CoreLib/Tools/GenUnicodeProp/CategoryCasingInfo.cs#L46-L60),
[string casing](https://github.com/dotnet/runtime/blob/4271d88e0aebf3d04f188f1334c2220d80555ef6/src/libraries/System.Private.CoreLib/src/System/Globalization/InvariantModeCasing.cs#L60-L123),
[encoded table lookup](https://github.com/dotnet/runtime/blob/4271d88e0aebf3d04f188f1334c2220d80555ef6/src/libraries/System.Private.CoreLib/src/System/Globalization/CharUnicodeInfo.cs#L253-L285).

The offline comparison hashes every upstream input, independently decodes the
release's three-level table for all 1,112,064 Unicode scalar values, and
compares the result with both the UCD-derived table and the checked-in TSV.
The 1,475 changed rows have SHA-256
`51e3c6f44c782e8e99c355b504f32900da56c9e4a500da83a15a2f807b95b6e4`.
The report lists every scalar on which the three tables differ. Its column
order is Unicode 15.1 with ICU, managed invariant Unicode 16.0, then Unicode
17.0 with ICU. Each row starts with the input scalar followed by the three
output scalars as decimal integers. There are 56 such rows. Pairwise counts
are 28 for ICU 15.1 versus managed, 29 for managed versus ICU 17.0, and 55
for the two ICU tables.

## Reproduction on Linux x64

From the checkout root, supply the pinned SDK in `global.json`, the existing
offline NuGet cache, and the private ICU 74.2 libraries as described in the
[two-profile C# readback](../legacy-keys/README.md). The following example
uses the host's ICU 78 for the third invocation. Set `IFW_TEST_ICU74` to the
absolute directory holding the original libraries. All three invocations use
the same executable and create fresh databases and simultaneous full-table
captures. The public source download is separate from the offline build and
comparison. Previously downloaded verified files can be reused.

```bash
tool="$PWD/tools/rust-qa/legacy-invariant"
run="$PWD/artifacts/rust/managed-invariant-study"
mkdir -m 700 "$run"
mkdir -m 700 "$run"/{home,cli,data,cache,config,empty-feed}
python3 -B "$tool/invariant_profile.py" fetch "$run/upstream"
python3 -B -m unittest discover -s "$tool"
study=(env -u LD_LIBRARY_PATH -u DOTNET_SYSTEM_GLOBALIZATION_INVARIANT
  -u DOTNET_SYSTEM_GLOBALIZATION_APPLOCALICU "HOME=$run/home" "DOTNET_CLI_HOME=$run/cli"
  "XDG_DATA_HOME=$run/data" "XDG_CONFIG_HOME=$run/config" "XDG_CACHE_HOME=$run/cache"
  DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_GENERATE_ASPNET_CERTIFICATE=false
  IFW_ORACLE_EXPECT_ARCH=x64 "NUGET_PACKAGES=$PWD/artifacts/nuget-packages")
"${study[@]}" dotnet restore "$tool/StoreIdentities.csproj" --source "$run/empty-feed" \
  --artifacts-path "$run/build" -p:EnableWindowsTargeting=false -p:NuGetAudit=false
"${study[@]}" dotnet build "$tool/StoreIdentities.csproj" --no-restore -c Release \
  --artifacts-path "$run/build" -p:EnableWindowsTargeting=false
probe="$run/build/bin/StoreIdentities/release/StoreIdentities.dll"
"${study[@]}" "LD_LIBRARY_PATH=$IFW_TEST_ICU74" DOTNET_SYSTEM_GLOBALIZATION_APPLOCALICU=74.2 \
  dotnet "$probe" capture "$run/older"
"${study[@]}" DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 dotnet "$probe" capture "$run/managed"
"${study[@]}" dotnet "$probe" capture "$run/current"
writers=("$run/older" "$run/managed" "$run/current")
"${study[@]}" "LD_LIBRARY_PATH=$IFW_TEST_ICU74" DOTNET_SYSTEM_GLOBALIZATION_APPLOCALICU=74.2 \
  dotnet "$probe" read "${writers[@]}" "$run/reader-older"
"${study[@]}" DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 dotnet "$probe" read "${writers[@]}" "$run/reader-managed"
"${study[@]}" dotnet "$probe" read "${writers[@]}" "$run/reader-current"
python3 -B "$tool/invariant_profile.py" compare "$run/upstream" \
  --writers "${writers[@]}" --readers "$run/reader-older" "$run/reader-managed" "$run/reader-current" \
  > "$run/comparison.json"
```

The legacy store writes both spellings for each of six name pairs and looks
them up again. Every sensitive database retains all 12. The insensitive
databases retain 11 entries with ICU 74, 10 with managed invariant casing,
and 8 with ICU 78. The fixture covers long s, Latin lambda with stroke,
dotless i, sharp s, Garay and Beria Erfe. The spelling written last wins
when a pair shares a key. Exact transfer history persists in all six
databases. The comparison opens finalized databases through immutable
SQLite URIs, checks all four tables against the raw C# observations, and
verifies the original file hashes again. The per-reader source counts in
the writer section come from direct SQL predicates using the three independently
derived keys.

Each actual reader opens six private copies of the three writers' original
databases. Each copy receives two ordinary store API queries for its source
listing. The first uses the original source spelling. The second supplies
the stored source key as a diagnostic spelling. Each query also looks up all
12 relative paths. The independent Python comparison repeats these lookups
with the reader's externally reconstructed scalar table against the immutable
original. It compares ordered entries, raw source and file spelling, exact
asset IDs, missing entries, account transfer time and the final copies' four
logical tables. The 18 combinations cover 36 source listings, 432 path
lookups and 18 transfer times. The reader's own `result.json` contains the
full API observations and before/after SHA-256 for each copy. Every reader
also emits its complete casing TSV, target, CoreLib build and assembly
digests. The ordinary two-profile readback has its own qualification
contract. [C# readback](../legacy-keys/README.md).

For the insensitive fixture's original mixed source spelling, only a reader
with the writer's profile finds the source. When supplied the stored ICU 17
source key, all three readers list its eight raw entries. The ICU 15,
managed 16 and ICU 17 readers resolve respectively 9, 10 and 12 of the
12 relative spellings on that database. Every sensitive combination returns
all 12 distinct names.

The `read-sizes` command exercises `GetAsync` and `GetSourceEntriesAsync`
on private copies before and after the [Rust file-size experiment](../storage/README.md#update-the-size-of-a-historical-entry-on-a-new-copy).
It records the active complete casing table, CoreLib and shipping Core
assembly digests with the observed paths, asset IDs and sizes.

## Attribution

The development TSV derives from the Unicode Character Database 16.0.0,
© 2024 Unicode, Inc. Include the complete Unicode License v3 notice when
redistributing that table. The source comparison reads checksum-pinned .NET
sources under the MIT license. [Unicode release notice](https://www.unicode.org/Public/16.0.0/ucd/ReadMe.txt),
[complete Unicode license](../legacy/licenses/Unicode-LICENSE.txt),
[.NET runtime license](https://github.com/dotnet/runtime/blob/4271d88e0aebf3d04f188f1334c2220d80555ef6/LICENSE.TXT).
