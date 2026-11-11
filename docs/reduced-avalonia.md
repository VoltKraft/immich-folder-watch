# Reduced Avalonia for the Linux application

## Scope and compatibility

PR #32 replaces the Linux application's upstream Avalonia/Fluent packages with
source-built variant **12.1.6.1**, derived from official **12.1.6** commit
`cf8e564674700348947e93ab19105f27afe859a9`. This is a project-specific package
version, not an official Avalonia release. The application stays AGPL-3.0-only
and .NET 10. Windows continues to use WPF; its MSI does not ship Avalonia.

The [component audit](avalonia-component-audit-20261111.md) confirms that earlier
v3.0.2 Linux bundles already contain the affected original 12.0.3 implementations.
This PR does not change existing release assets. Package-level MIT metadata and
successful tests do not establish the licenses of every compiled component.

The reduction removes MS-PL calendar, calendar-date-picker and autocomplete
implementations and resources, the Silverlight-derived layout transform, and
dependent unused templates. The exact inventory is
[`removals.json`](../packaging/avalonia-reduced/removals.json). Popup templates use
`Decorator`/render transforms instead of the removed layout-transform control.
The application does not use transformed popups or the removed controls. Future
features needing them require a compatible implementation and new validation.
Dropdown and tooltip opening in both themes have explicit GUI regression tests.

Only `Avalonia.Controls.dll` and the Fluent theme are reconstructed. Retained
net10.0 framework assemblies and build tools come from hash-verified official
packages; original copies of replaced assemblies and unsupported framework
variants are removed. Original notices remain unchanged; additional retained
SixLabors Apache-2.0 and Apple BSD-2-Clause attribution is packaged separately.

## Build and restore

Python 3.11+ and the **exact .NET SDK version in
[`inputs.json`](../packaging/avalonia-reduced/inputs.json)** are required (currently
10.0.401, aligned with the Flatpak SDK and root `global.json`). Install that SDK alongside other SDKs;
preparation must not silently substitute a newer compiler.

Explicit preparation, used by CI:

```bash
python3 tools/prepare_reduced_avalonia.py
python3 tools/verify_reduced_avalonia.py \
  --assets src/ImmichFolderWatch.App.Linux/obj/project.assets.json
```

Run the verification after restore. On Windows use `python` if `python3` is not
available. `--dotnet /path/to/dotnet` selects an existing SDK installation.
Preparation downloads only hash-pinned official source/package inputs and builds
both private packages into ignored `artifacts/reduced-avalonia/feed`.

[`NuGet.Config`](../NuGet.Config) maps the two private package IDs exclusively to
that feed, with exact package references. Other packages use nuget.org. The
package cache is repository-local `artifacts/nuget-packages`; normal preparation
does not replace official packages in the user's global cache.

A narrow [`Directory.Build.targets`](../Directory.Build.targets) restore hook
prepares these packages for the Linux app before package-reference collection.
This supports IDEs and GitHub-managed dependency submission, which cannot run a
custom CI step. `--if-needed` reuses only a feed whose input/recipe fingerprint and
both archive hashes match its completed build record. Preparation is serialized
with an OS lock. Explicit CI preparation rebuilds; unrelated projects do not
execute the hook. Do not run another preparation while a restore using the same
cache is active.

The offline feed generator builds into an isolated temporary feed, then supplies
`ReducedAvaloniaPrepared=true` only for its already-prepared restore. Flatpak
rebuilds the same packages offline from the pinned source archive and official
NuGet inputs; generated private packages from a developer machine are never
release inputs. All external source/archive hashes and the exact compiler are
part of the reconstruction contract.

## Verification and maintenance

```bash
python3 tools/verify_reduced_avalonia.py --publish artifacts/linux-publish
python3 tools/audit_reduced_avalonia.py artifacts/linux-publish
python3 -m unittest discover -s tools/tests -p '*reduced_avalonia*.py' -v
```

The publish verifier checks restored archive bytes against the current rebuilt
feed, provenance against source/removal inputs, and published DLL bytes against
the reduced packages. The static binary auditor reads PE/CLI type definitions
without executing assemblies and rejects excluded implementations. Hash checks,
source review, resource inspection and behavioral tests are complementary.

Any future Avalonia change requires a fresh component/license audit, new immutable
input pins, coherent companion versions, a new private variant version, provenance
and negative-control checks, GUI tests and both native Flatpak builds. Never
reuse a shipped variant version for changed inputs. Preserve assembly source
metadata so an enclosing application Git revision does not alter framework bytes.

D-Bus is aligned to **Tmds.DBus.Protocol 0.94.1** in the Linux app and portable
protocol-test project. Its exact-source MIT license is retained; synthetic portal
and tray tests validate integration without connecting to a live Immich server.
