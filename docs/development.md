# Development

## Rust rewrite reference corpus

The selected RW-01 through RW-07 goal and its gates live in the
[project brief](project.md#m-rust-implementation-20261114) and
[acceptance record](rust/acceptance.md). Work only on `rewrite/rust`.
The shipping .NET sources remain the behavioral reference. The C# oracle is
development tooling; it is never part of the Rust candidate runtime.

Run from the repository root with the exact SDK selected by `global.json`:

```bash
dotnet run --project tools/RustCompatibilityOracle/RustCompatibilityOracle.csproj -- verify rust/tests/fixtures/legacy
dotnet test src/ImmichFolderWatch.Tests.Core/ImmichFolderWatch.Tests.Core.csproj -c Release --filter FullyQualifiedName~RustRewriteBehaviorContractTests
dotnet test src/ImmichFolderWatch.Tests.Linux/ImmichFolderWatch.Tests.Linux.csproj -c Release --filter FullyQualifiedName~RustRewriteLifecycleContractTests
```

Golden verification requires the reviewed corpus for the current OS. Generate
new candidate output using `export artifacts/rust/oracle`, review it and compare
an independent `verify artifacts/rust/oracle` run before adding golden fixtures.
Export-then-verify proves repeatability, not equivalence to an already reviewed
baseline. See [storage provenance and limits](rust/rw01-storage-contract.md).
No command takes a production profile/database; all profiles/media are synthetic.

`IFW_ORACLE_EXPECT_ARCH=x64` or `arm64` requires matching OS/process architecture
and prevents emulated/cross-target runs from being counted as native evidence.
The behavior/lifecycle tests find fixtures by walking their repository ancestors;
`IFW_COMPATIBILITY_REPOSITORY` can identify the source checkout for relocated
test binaries. It selects fixtures, never an application profile.

Use separate `--artifacts-path artifacts/rust/<lane>` directories for concurrent
reference builds. A local exact SDK is available in the existing ignored cache at
`artifacts/flatpak-local-2.11.2/sdk/dotnet` on the current development machine;
this is local convenience, not a portable install prerequisite. `DOTNET_CLI_HOME`
can isolate SDK state; set `DOTNET_GENERATE_ASPNET_CERTIFICATE=false` and
`DOTNET_CLI_TELEMETRY_OPTOUT=1`. Test-host/MSBuild sockets and isolated D-Bus
protocol tests need local IPC access; a sandbox rejection is not a failed behavior test.

`rust-compatibility.yaml` runs on `rewrite/rust` for corpus/source changes and
manual dispatch on that branch only, using native Windows/Linux x64/ARM64 runners.
It uploads reference evidence under the exact source SHA, has read-only repository
permissions and cannot publish releases. SDK architecture selection is supported
by the [pinned setup action](https://github.com/actions/setup-dotnet/blob/0f4a354dd5547a28c70b7853dbd95d5b67886e73/action.yml);
runner availability follows the [GitHub runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
Actual runs, missing platforms and independent workflow review belong in the
acceptance record. Native reference tests do not qualify the future Rust GUI.

## Rust feasibility workspace

Use `rust/Cargo.toml` on `rewrite/rust`. Development crates use the unpublished
workspace version `0.0.0`. Product release numbering remains in
`Directory.Build.props`. Pin the compiler in `rust/rust-toolchain.toml` and the
upstream distribution hashes in `rust/toolchain-inputs.json`. Keep `rust/Cargo.lock`
under version control. The workspace currently exercises native feasibility.

From the repository root on Linux x64, install the pinned distribution into
the ignored build directory and run the same probes as the native workflow:

```bash
bash tools/rust-qa/install-toolchain.sh x86_64-unknown-linux-gnu
export PATH="$PWD/artifacts/rust/toolchain/bin:$PATH"
export CARGO_HOME="$PWD/artifacts/rust/cargo-home"
python3 tools/rust-qa/test-native.py x86_64-unknown-linux-gnu
```

Use the matching target from the inputs file on Linux ARM64 and on Windows
with Git Bash and MSVC build tools. The installer requires curl, sha256sum,
tar with XZ support and Python 3.11+. It checks the archive before extracting
and installs under `artifacts/rust/toolchain`. A host with an equivalent native
compiler can supply it through `PATH`. The test driver checks the release, full
compiler revision and native host. Its logs and per-step results live under
`artifacts/rust/feasibility/<target>/`. `Rust native feasibility` runs the
same commands and retains evidence under the source SHA. The five C# window
traces exercise the Rust policy. Native window, tray and assistive-technology
observations have separate entries in the [acceptance record](rust/acceptance.md).
The same run compares Rust path, timestamp and casing observations to a native
.NET 10.0.401 development oracle. Make both SDKs available on `PATH` for this
comparison. See the [legacy checks](rust/rw02-legacy.md).

Run `python3 tools/rust-qa/verify-gui-inputs.py` to verify the original font and
supplemental notice bytes offline. `--fetch-missing` restores a missing input
by its reviewed upstream revision and digest. For the separate development GUI
assessment, fetch its lock once and generate one source and feature inventory
per supported target. For example, from the repository root:

```bash
cargo fetch --locked --manifest-path tools/rust-qa/gui/Cargo.toml
python3 tools/rust-qa/audit-graph.py tools/rust-qa/gui/Cargo.toml x86_64-unknown-linux-gnu artifacts/rust/gui-run/audit/x86_64-unknown-linux-gnu.json
```

The [desktop input review](rust/rw02-gui-dependencies.md) records embedded
third-party code and protocol terms that require additional notices. From an
isolated native test host, use these maintained assessment entry points with
the matching toolchains on `PATH`. Use fresh output directories for each run.

```bash
python3 tools/rust-qa/storage/run.py x86_64-unknown-linux-gnu --output artifacts/rust/storage-native/test
python3 tools/rust-qa/yaml/run.py x86_64-unknown-linux-gnu --output artifacts/rust/yaml-assessment/runs/test
python3 tools/rust-qa/realtime/run.py x86_64-unknown-linux-gnu --output artifacts/rust/realtime-native/test
python3 tools/rust-qa/build-gui-probe.py x86_64-unknown-linux-gnu
python3 tools/rust-qa/gui/native.py --backend x11 --input
python3 tools/rust-qa/gui/native.py --backend wayland --input --present-mode mailbox
```

The [four-target assessment workflow](../.github/workflows/rust-desktop-assessment.yaml)
records native Rust and C# storage results, loopback sessions, graph digests,
adapters and observed window transitions. Windows uses the fixture's inherited
control pipe and checks real Win32 show events and `WM_CLOSE` for the child
PID. The Linux observer runs on a private X11 or Wayland desktop. See the
[native GUI report](rust/rw02-native-gui.md) for the desktop prerequisites,
measured presentation modes and remaining checks.

The [YAML assessment](rust/rw02-yaml.md) uses the shipping C# reader in both
directions. Upload only its individual run output. The separate private cache
contains original third-party archives. The [Linux service tests](rust/rw02-linux-services.md)
exercise tray-owner changes and actual synthetic Documents grants. On a native
Linux builder, set `IFW_QA_REFERENCE_SDK` to the root of the pinned .NET SDK
and `IFW_QA_REFERENCE_PACKAGES` to a populated NuGet cache below `artifacts/`.
The grant oracle mounts both read-only and restores offline. The hosted job
populates this package cache while building the earlier storage and YAML oracles.
The
[portal comparison builder](rust/rw02-portal-upstream.md) replays one upstream
fix on exact release sources in an offline SDK. It writes the executable to
the ignored test area for the private namespace. The
[Windows service tests](rust/rw02-windows-services.md) exercise per-user
shortcut registration, Shell notifications and independent UI Automation.
The [native folder chooser fixture](rust/rw02-portal-dialog.md) exercises
X11 and Wayland parents, selection and denial. The local Flatpak variant
installs an isolated test app in a temporary repository. The GNOME variant
checks its on-screen notification and autostart registration and removal.

## Build

The Linux UI uses the [reduced Avalonia build](reduced-avalonia.md). Python 3.11+
and the exact SDK pinned in `packaging/avalonia-reduced/inputs.json` are required
for its source reconstruction. Normal restore prepares the private packages;
CI also runs explicit preparation and provenance verification. Follow that guide
for offline feeds, cache boundaries and future framework updates.

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

Async autostart view-model tests must run on a single UI synchronization context,
matching the documented UI-thread contract. `SingleThreadUiContext` pumps their
continuations on one dedicated thread; platform fakes and property notifications
assert thread affinity. Do not replace it with a dispatcher that treats arbitrary
thread-pool threads as the UI thread.

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

### Windows MSI upgrade checks

Windows CI builds x64 and ARM64 MSI candidates through `build-msi.ps1`, which
validates the compiled shutdown/abort/removal sequence with
`Test-InstallerUpgradeContract.ps1`. Run the focused checker tests with:

```powershell
python -m unittest discover -s tools/tests -p test_windows_installer.py -v
python -m unittest discover -s tools/tests -p test_msi_upgrade_contract.py -v
python -m unittest discover -s tools/tests -p test_installed_upgrade.py -v
```

The PowerShell execution tests require `pwsh` (or `IFW_TEST_PWSH`). Windows CI
also runs `Test-InstalledUpgrade.ps1` on a fresh hosted runner for a real x64
upgrade attempt while the released application is running. It verifies either
completion or explicit safe refusal with the complete baseline retained, followed
by normal tray-menu Quit and a successful retry. Inspect the outcome
and MSI logs; neither a retry nor fixture tests prove automatic MSI shutdown.
See [Windows packaging](../packaging/windows/README.md#upgrade-process-safety)
for the test-only MSI version and reboot/ARM64 boundaries.

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
