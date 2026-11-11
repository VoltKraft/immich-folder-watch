# Development

## Build

```bash
dotnet restore
dotnet build ImmichFolderWatch.sln -c Debug
```

The app build generates branding assets automatically from `assets/branding/logo.svg`
into `artifacts/branding/`.

### Branding

The logo source is the open golden folder with a compact five-color flower. The
petals are individually rotated 6 degrees clockwise and moved toward the center;
their spacing exposes the folder color without white outlines. Its transparent
`1024 x 820` viewBox fits the artwork without an outer border or additional padding.
Keep this tight crop when editing the source: the generator preserves the aspect
ratio and centers it in square PNG and ICO frames, using their full width. The
remaining space above and below is transparent and preserves the folder's proportions.
Edit the SVG rather than generated assets. To regenerate only the branding assets:

```bash
dotnet build tools/BrandAssetGen/BrandAssetGen.csproj -c Debug
```

## Test

```bash
dotnet test ImmichFolderWatch.sln -c Debug
```

On Linux, build the Avalonia host and run both portable and Linux GUI tests:

```bash
dotnet build src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj -c Debug
dotnet test src/ImmichFolderWatch.Tests.Core/ImmichFolderWatch.Tests.Core.csproj -c Debug
dotnet test src/ImmichFolderWatch.Tests.Linux/ImmichFolderWatch.Tests.Linux.csproj -c Debug
```

The GUI tests use actual Avalonia controls in an isolated headless application.
See [the test fixture guide](../src/ImmichFolderWatch.Tests.Linux/README.md) for
synthetic screenshots, test-only dependency licenses, and coverage boundaries.
Portal protocol tests use an isolated `dbus-daemon` and `xdg-dbus-proxy` on Linux. Desktop-specific
acceptance remains in [Linux smoke tests](qa/linux-smoke.md).

Worker integration tests must wait for durable completion before stopping the
worker or removing its temporary database. A fake client's transfer counter can
advance before timestamps and sync state have been persisted. For initial sync,
use `InitialReconciliationLogger` with the configured source count to wait for
both reconciliation passes, then stop the worker and inspect the persisted state.
Windows rejects deleting an open SQLite database; Linux unlink behavior can hide
background operations that a test has not waited for.

## Run

```bash
dotnet run --project src/ImmichFolderWatch.App
```

The app reads its config from `%LOCALAPPDATA%\Immich Folder Watch\config.yaml`. Use the GUI's **Save and Apply** to write it.

## CI

- `ci.yaml`: cross-platform build + test coverage for the codebase, plus native
  x86_64/aarch64 candidate builds through `flatpak-validation.yaml`. Candidate
  packages use the `test` Flatpak branch and do not create a release. The reusable
  workflow takes its source commit directly from the caller's `github.sha`
  event context; it does not accept a separate source-ref input. Checkout,
  manifest preparation and artifact names all use that same commit.
- `pages-artifact-validation.yaml`: called by CI with read-only repository
  permissions; uploads synthetic Pages fixtures through the production action pin,
  downloads them by artifact ID and verifies tar contents, hidden-file selection
  and link dereferencing. It never deploys Pages or accesses signing secrets.
- `release.yaml`: build x64 and ARM64 Windows MSIs and Linux Flatpaks from the
  same immutable commit, then publish all four only after successful CI on
  `main` and only when the version tag does not already exist
- `flatpak-pages.yaml`: import the latest published Linux bundles into a signed
  GitHub Pages repository, with `.flatpakref` installation and Flatpak updates;
  explicitly dispatched after release publication (also supports manual recovery).
  See the [repository deployment guide](../packaging/flatpak/pages.md).
- `winget.yaml`: generate and submit the two-architecture WinGet manifest after
  the GitHub Release has been published
- `flathub.yaml`: prepare and build both architectures after publication, then
  optionally submit updates to the accepted Flathub app; see the
  [activation guide](../packaging/flatpak/flathub/README.md)
- `packaging/flatpak/`: the shared Flatpak manifest, metadata, local-build
  instructions, and Flathub submission requirements

### Publication workflow trust

The Flatpak release job explicitly checks out the repository's default branch and
requires its exact HEAD to equal the resolved release target before running any
repository script. This keeps the SDK, manifest template and generated offline
NuGet feed consistent with the commit pinned into the release manifest. If main
advances between target resolution and checkout, the job fails closed; after CI
passes on current main, use its automatic release run or retry Release on main.
Do not remove the guard or substitute an arbitrary checkout ref to retry an old
run. Existing main/same-repository event gates and immutable release tags remain.

Focused workflow and manifest regression checks:

```bash
python3 -m unittest discover -s tools/tests -p test_workflow_security.py -v
python3 -m unittest discover -s tools/tests -p test_prepare_flatpak_release_manifest.py -v
```

Release build jobs use read-only repository permissions and checkout does not
persist credentials. Only the publishing job receives `contents: write`; the
separate downstream-dispatch job receives `actions: write`. Actions are pinned
to verified commit SHAs, the Flatpak tooling image uses a multiarchitecture OCI
digest, and WinGet submission verifies a fixed executable SHA-256 before use.
The pins and license evidence are described in the packaging guides and security
remediation record. Updating pins requires upstream provenance/license verification.

## Dependency updates

[Dependabot configuration](../.github/dependabot.yml) checks NuGet packages in
`src/*` and `tools/BrandAssetGen`, and GitHub Actions in all workflows, every Monday
at 08:00 Europe/Berlin. Each ecosystem permits up to five open version-update PRs.
Avalonia, Microsoft.Extensions, SkiaSharp and xUnit packages are grouped by family
for version updates; other packages and Actions remain individually reviewable.
Major-version proposals are allowed and require compatibility review. PR titles
and commits use `chore(deps)`.

The configuration takes effect when present on GitHub's default branch. Check
**Insights > Dependency graph > Dependabot** for the first hosted runs and their
logs. Alerts and automatic security updates are separate repository settings;
both are enabled for this repository, with activation evidence in
[project status](status.md#dependabot-activation-2026-11-10). The YAML file alone
does not enable them. The weekly schedule and version-update PR limit
do not govern security updates. See GitHub's
[configuration reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference).

The `xunit.v3` ignore rule uses `>= 4.0.0` until the Avalonia headless bridge
supports xUnit 4 and the VSTest workflow is validated. Keep this absolute version
exclusion for both version and security updates. The hosted updater rejects the
interval spelling `[4.0.0,)` with `illformed_requirement`, even though the separate
YAML configuration check accepts it. Validate updater runs after changing ignore
requirements; a green configuration check alone is insufficient.

Before merging any proposal, verify upstream provenance and license compatibility
with **AGPL-3.0-only**, refresh affected third-party notices/license catalogs, and
require the existing Windows/Linux application and native Flatpak CI checks.
Review Avalonia's component licensing for the proposed version. Preserve full
commit-SHA action pins and their version comments. Dependabot PRs use the existing
read-only `pull_request` CI without publication credentials. Repository auto-merge
is disabled, and no automatic merge workflow is configured. Both security and
version-update PRs require manual review and merging.

The .NET SDK/runtime, Flatpak SDK archive URLs/checksums, build-container digest,
and WinGet submission binary/checksum remain manually coordinated updates under
the packaging guides. Dependabot's `github-actions` ecosystem does not update
workflow container images. Generated Flatpak NuGet sources are regenerated by
the existing candidate/release tooling, not edited by hand. This configuration
does not change package versions or validate any proposed upgrade in advance.

## Project Conventions

- Keep user-facing logs in English.
- Keep comments concise and in English.
- Avoid coupling watcher/worker orchestration with HTTP details.
- Keep Core project free of runtime host concerns.
