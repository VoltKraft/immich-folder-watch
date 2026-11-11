# Reduced Avalonia inputs and package contract

Immich Folder Watch remains AGPL-3.0-only. `inputs.json` identifies official
Avalonia 12.1.6 source commit `cf8e564674700348947e93ab19105f27afe859a9`, three
upstream NuGet compiler inputs and the exact .NET 10.0.401 SDK. The checked-in
archive hashes are SHA-512. `removals.json` records every removed source and
modified theme aggregator/popup resource.

The private version **12.1.6.1** belongs to this application's reduced variant.
It is not an upstream Avalonia release and must not be reused for a different
published recipe. Only `Avalonia` and `Avalonia.Themes.Fluent` are reconstructed;
other reviewed companion packages remain official 12.1.6. The reconstructed
packages support net10.0 only. Their Controls/Fluent implementation and reference
assemblies are replaced, while other upstream assemblies and original notices
are preserved. Their strong-name identity is delay-signed for compatibility;
it does not assert upstream authorship or authenticity of the modified code.

## Preparation and restore

From the repository root, with .NET 10.0.401 available:

```sh
python3 tools/prepare_reduced_avalonia.py --dotnet dotnet
```

The default input/work directory is `artifacts/reduced-avalonia`; the output
feed is `artifacts/reduced-avalonia/feed`. `--source-root`, `--work-dir`, `--output`
and `--dotnet` support isolated builds. The preparer downloads only the locked
URLs and verifies hashes before extraction or compilation. The low-level builder
uses no package feeds or network access.

`--if-needed` reuses output only when `ready.json` matches the current manifests,
all four framework scripts and the exact bytes of both generated archives. An OS
file lock serializes preparation in the same work directory and releases after
failure or process exit. After a successful preparation, only stale cache entries
for the two current private package identities are removed; unrelated versions
and packages remain intact. Do not concurrently restore into that same cache
while explicitly rebuilding the framework.

The root `NuGet.Config` maps the two exact package IDs exclusively to the private
feed; nuget.org cannot silently replace a missing reduced package. Its default
package cache is repository-local `artifacts/nuget-packages`. Explicit
`NUGET_PACKAGES` overrides retain normal NuGet behavior. All generated artifacts,
source downloads and package caches are ignored by Git.

## Offline build and validation

The Flatpak workflow stages the same hash-pinned inputs. Its builder invocation
is equivalent to:

```sh
python3 tools/build_reduced_avalonia.py \
  --source-archive /path/to/avalonia-source.tar.gz \
  --upstream-packages /path/to/official-nupkgs \
  --output artifacts/reduced-avalonia/feed \
  --work-dir /path/to/empty-build-directory \
  --dotnet /path/to/dotnet
```

Each archive embeds `reduced-avalonia.json`, source revision/hash, removal
inventory, and rebuilt assembly SHA-256 hashes. Assembly informational metadata
is pinned to the upstream revision, and deterministic paths/archive metadata
avoid incorporating the application's checkout path or Git commit.

```sh
python3 tools/verify_reduced_avalonia.py \
  --assets src/ImmichFolderWatch.App.Linux/obj/project.assets.json \
  --publish /path/to/published-app
python3 -m unittest discover -s tools/tests -p 'test_*reduced_avalonia.py' -v
```

Verification requires exact private package identities, fresh-build/archive
byte equality, current provenance/removal records, and matching deployed DLLs.
The PE/CLI audit reads TypeDef metadata without executing assemblies and rejects
removed controls, including the nested autocomplete helper. It inspects runtime
and reference DLLs in package archives and all managed DLLs in a publish tree.
This complements source/resource review and real GUI regression tests; it is not
a general license scanner.

The app does not use the removed calendar, autocomplete, date/time theme,
notification or progress templates. Popup wrappers use `Decorator` with a render
transform instead of the removed Silverlight-derived layout-transform control.
Ordinary app dropdowns and tooltips are regression tested; transformed popup
measurement is not a supported feature of this private variant. Future features
needing excluded controls or transformed popup layout require a compatible
implementation and a new review.
