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

### Download activity, backups and restart

The portable Core test `Download_RetainsBeforeAndAfterBackupsAndRestartsFromLatest`
runs the shipping worker twice against the same disposable watch root. To retain
the two SQLite backups, the downloaded file and the observer's JSON, set
`IFW_QA_ACTIVITY_OUTPUT` to a fresh absolute directory for the test process.
For example, on Linux x64 with SDK 10.0.401, use a clean checkout of the revision
under test and run the following from the repository root.

```bash
export IFW_QA_ACTIVITY_OUTPUT="$PWD/artifacts/rust/worker-activity"
dotnet test src/ImmichFolderWatch.Tests.Core/ImmichFolderWatch.Tests.Core.csproj -c Release \
  --filter FullyQualifiedName~Download_RetainsBeforeAndAfterBackupsAndRestartsFromLatest \
  --logger 'trx;LogFileName=core-reference.trx' --results-directory artifacts/rust/test-results
python3 -B tools/RustCompatibilityOracle/verify_activity.py "$IFW_QA_ACTIVITY_OUTPUT" \
  artifacts/rust/test-results/core-reference.trx linux x64 "$(git rev-parse HEAD)"
```

The same reader works on a downloaded archive. Supply the original target
(`linux` or `windows`), architecture (`x64` or `arm64`) and full source revision.
The checkout needs that commit and the 3.0.4 reference commit. The reader uses
immutable SQLite connections and prints a JSON receipt with the original hashes.
The test uses an in-process synthetic Immich peer. [Activity and source checks](rust/rw01-storage-contract.md#download-activity-and-the-latest-backup).

The native Rust backup trials cover a download, an upload, a propagated
deletion and an interrupted timestamp repair. Each restarted C# worker
opens bytes returned by Rust. Separate synthetic peers retain the uploaded
asset or trashed contents. The repair fixture keeps the same physical file
across the database restore. Each `rust-worker-backup` archive contains the
source, build records and original data for detached replay.
[Download and upload](../tools/rust-qa/storage/README.md#restore-after-a-synthetic-download) · [Deletion and repair](../tools/rust-qa/storage/README.md#restore-after-a-deletion-or-interrupted-repair).

### Repair and deletion after restoring the worker database

The Core reference suite can export an interrupted timestamp repair and a
local deletion propagated to the peer. Set `IFW_QA_REPAIR_ACTIVITY_OUTPUT`
and `IFW_QA_DELETION_ACTIVITY_OUTPUT` to separate fresh absolute
directories. The native reference workflow retains the databases, media,
xUnit report and three first-party assemblies in each `rust-reference`
archive. From the repository root, replay each case against the commit
that produced the archive. Here `archive` is its extracted directory and
`revision` is the full commit ID.

```bash
for kind in repair deletion; do
  python3 -B tools/RustCompatibilityOracle/verify_rollback.py "$kind" "$archive/worker-$kind" \
    "$archive/test-results/core-reference.trx" "$archive/worker-assemblies" linux x64 "$revision"
done
```

Pass the archive's actual operating system and architecture. The reader
checks the loaded assembly hashes, immutable databases, raw media and the
test execution that produced each manifest. [Reference behavior](rust/rw01-storage-contract.md#external-state-after-deletion-and-timestamp-repair).

### Original package install and repair

Use the common runner on a native Linux x64 or ARM64 machine with Flatpak,
OSTree, Bubblewrap, `dbus-run-session` and `dbus-send`. It creates a private
bus inside the test namespace, a fresh Flatpak installation and an evidence
directory. From the repository root, a local x64 run with a previously
downloaded release bundle is:

```bash
python3 -B tools/RustCompatibilityOracle/installed/run.py linux-x64 \
  artifacts/rust/shipping-install-linux-x64 \
  --package artifacts/rust/legacy-installer-inputs/v3.0.4/immich-folder-watch-3.0.4-linux-x64.flatpak
```

Supply a fresh output directory each time. Omitting `--package` downloads
the exact published asset. The Windows executor requires the matching
disposable GitHub-hosted Windows runner on `rewrite/rust`. The four-target
workflow uploads the native logs, retained synthetic profile and evidence
hashes. The [separate Fedora x64 launch test](rust/rw01-installed-packages.md#two-ordinary-launches-of-the-installed-linux-x64-reference) runs the signed 3.0.4 Flatpak twice on a private X11 desktop.
The [Ubuntu x64 and ARM64 launch jobs](rust/rw01-installed-packages.md#signed-native-launch-inputs-on-ubuntu-x64-and-arm64)
stage the original release bundle, detached signature, signed Freedesktop
Platform and native GL extension before running the same offline observer.
The [configured upload trial](rust/rw02-instance.md#rust-startup-during-a-signed-worker-upload)
holds a real transfer from that signed app while a worker-enabled Rust
launch attempts to take ownership. Its test peer and both installed refs
run inside the same disposable network namespace.
[Original packages and results](rust/rw01-installed-packages.md) · [Installer workflow](../.github/workflows/rust-legacy-install.yaml).

### Installed Flatpak worker backup on Fedora x64

Use the existing isolated Cargo home, NuGet cache, native toolchain, signed
3.0.4 bundle and source-bound GUI and worker from the [configured upload
trial](rust/rw02-instance.md#rust-startup-during-a-signed-worker-upload).
Choose a fresh storage output directory. The following paths match the
local build layout used for the native result.

```bash
env PATH="$PWD/artifacts/rust/toolchain/bin:$PATH" CC=/usr/bin/gcc \
  NUGET_PACKAGES="$PWD/artifacts/rust/native-insert-local-cache-01/nuget" \
  python3 -B tools/rust-qa/storage/run.py x86_64-unknown-linux-gnu \
  --offline --cargo-home artifacts/rust/storage-assessment/cargo-home \
  --dotnet artifacts/flatpak-local-2.11.2/sdk/dotnet --installed-upload-backup \
  --output artifacts/rust/storage-native/installed-upload-repeat

python3 -B tools/RustCompatibilityOracle/installed/interop/assess.py \
  --gui-build artifacts/rust/gui-dual-election-01 \
  --inventory-subject artifacts/rust/performance/subjects/linux-dual-election-8e1c5d7 \
  --shipping-upload --rust-backup artifacts/rust/storage-native/installed-upload-repeat
```

The native run used the direct system C compiler and pinned Rust 1.100.0
and SQLite 3.54.1. Preserve the two original HTTP image bodies, both
permission probes, original main/WAL, source build receipt, returned
database and the database after the signed application's second Quit.
[Executed trial and digests](rust/rw01-storage-contract.md#installed-fedora-worker-resumes-from-a-live-rust-backup).

### Installed worker handover on native Ubuntu runners

The Linux desktop assessment uses the same installed application ID and
two private Flatpak branches on x64 and ARM64. It builds the Rust backup
helper offline from the inputs cached by the native storage job. The GUI
build, its inventory worker, the helper and the signed .NET 3.0.4 apphost
must match the runner architecture. The observer checks the GUI sources
against the checkout's Git objects and the worker against its native build
digest. It verifies the detached signatures before the two applications
share a disposable profile and loopback peer.

The workflow passes `--hosted-runtime` with the verified Platform
deployment and `--rust-backup` with the completed offline storage result
to the preceding `assess.py` command. In the `rust-installed-handover`
artifact, `inputs.json` identifies the executables, signed release and
source archives. `evidence.sha256` covers the original HTTP bodies,
SQLite main file and WAL, returned backup, restarted database and
both apphosts' logs. The Fedora x64 regression and its independent
row-by-row readback are recorded in the [installed storage contract](rust/rw01-storage-contract.md#native-linux-handover-and-backup-observer).
The [desktop workflow](../.github/workflows/rust-desktop-assessment.yaml) owns the Ubuntu runs.

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
comparison. The native command also checks that its complete C# casing map
matches a separately reproduced Unicode table before qualifying the Rust
comparison. [Legacy checks and source pins](rust/rw02-legacy.md#independently-reproduced-casing-profiles).

A second process runs the same compiled oracle with managed invariant casing.
Both invocations select the installed Microsoft.NETCore.App 10.0.12 runtime
with roll-forward disabled. The development machine needs that patch
alongside SDK 10.0.401. The receipt verifies the loaded assembly and CoreLib.
`managed-scalar-reference/manifest.json` records CoreLib
and the scalar payloads. `managed-legacy.json` records the independently
derived table used by Rust and the complete comparison. On a local repeat
pass `--output artifacts/rust/feasibility/<fresh-name>` to `test-native.py`
to preserve earlier receipts. [Managed profile and storage behavior](rust/rw02-legacy.md#managed-globalization-invariant-casing-in-net-10012).

The native command also writes `workspace-boundaries.json` for the selected
target. It checks the resolved Cargo dependencies of each workspace member
against its role. A new member needs an explicit role. The generic crates
must stay independent of Immich, and presentation dependencies belong in
the presentation layer. [Dependency direction](rust-desktop-standard.md#rds-01-dependency-direction)
· [Cargo graph check](../tools/rust-qa/workspace-boundaries/check.py).

The [native watch test](rust/rw02-watch-events.md) exercises the retained
directory handles, bounded change hints and periodic inventory fallback.
Each native feasibility job uploads the target's result and digest.

The dependency-free `desktop-platform-log` crate provides the native log
outputs assessed in RW-02. The log observer compares file bytes with the
shipping provider, then reads back native events using the host OS. It uses
an isolated journal on Linux and a temporary custom log on the disposable
Windows runner. [Platform log commands and results](rust/rw02-platform-logs.md).

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
python3 tools/rust-qa/storage-faults/run.py x86_64-unknown-linux-gnu --cargo-home artifacts/rust/storage-cargo-home --output artifacts/rust/storage-faults/test --tmpfs
python3 tools/rust-qa/yaml/run.py x86_64-unknown-linux-gnu --output artifacts/rust/yaml-assessment/runs/test
python3 tools/rust-qa/instance/run.py x86_64-unknown-linux-gnu --output artifacts/rust/instance-native/test
python3 tools/rust-qa/realtime/run.py x86_64-unknown-linux-gnu --output artifacts/rust/realtime-native/test
python3 tools/rust-qa/build-gui-probe.py x86_64-unknown-linux-gnu
python3 tools/rust-qa/gui/profile_text.py
python3 tools/rust-qa/gui/native.py --backend x11 --input
python3 tools/rust-qa/gui/native.py --backend wayland --input --present-mode mailbox
python3 tools/rust-qa/gui/native.py --backend wayland --wayland-ime --monitor-changes
```

The [four-target assessment workflow](../.github/workflows/rust-desktop-assessment.yaml)
records native Rust and C# storage results, loopback sessions, graph digests,
adapters and observed window transitions. The transport's `sessions.json`
includes the [packets received by the peer on shutdown](rust/rw02-realtime-transport.md#stopping-an-established-session).
Each target uploads the native transport report, checksums and logs in
`rust-realtime-<target>-<commit>` before it starts the desktop trials.
Windows uses the fixture's inherited
control pipe and checks real Win32 show events and `WM_CLOSE` for the child
PID. The Linux observer runs on a private X11 or Wayland desktop. See the
[native GUI report](rust/rw02-native-gui.md) for the desktop prerequisites,
measured presentation modes and remaining checks.

After staging the integrated Linux GUI and worker, run
`python3 -B tools/rust-qa/performance/worker/check_hidden.py STAGED_SUBJECT --second-launch`.
It starts the ordinary executable twice on a private X11 desktop, once with
no arguments and once with `--background`. It checks the actual D-Bus owner,
window, inventory worker, file rediscovery and shutdown. The separate
`gui/native.py` lifecycle checks exercise the ordinary launch on X11 and Wayland.
[Linux second-launch results](rust/rw02-instance.md#ordinary-second-launch-of-the-linux-gui).

On local x64, `python3 -B tools/rust-qa/gui/flatpak/run.py STAGED_SUBJECT`
repeats both launches from an installed synthetic Flatpak using the pinned
public Platform and graphics extension. The GUI, proxy and window are
observed separately. The script uses a disposable offline repository.
[Installed Flatpak trial](rust/rw02-instance.md#second-launch-through-the-installed-flatpak).

The Windows assessment runs the ordinary launcher first, followed by
`python -B tools/rust-qa/windows-launcher/native_tray.py <native-target>`
on the disposable x64 and ARM64 runners. The latter starts the elected GUI
and its inventory worker, reads the Shell registration and observes the window
and worker across activation and quit. It writes its result and raw logs to
`artifacts/rust/windows-gui-tray/<native-target>/`.
[Primary GUI and Shell callback](rust/rw02-windows-services.md#primary-gui-and-shell-callback).

After building the retained window, run both ordinary Windows observers
with the same native target and `--subject retained`.

```powershell
python -B tools/rust-qa/windows-launcher/observe.py $env:NATIVE_TARGET --subject retained
python -B tools/rust-qa/windows-launcher/native_tray.py $env:NATIVE_TARGET --subject retained
```

The first command observes the ordinary second launch. The second also
closes a visible window, invokes the original Shell icon and checks the
return of the same HWND, focused editor, worker and DX12 generation.
Read the per-case results in `rust-retained-activation-<target>-<commit>`.
The complete desktop archive includes the paired build receipts, raw Cargo
compiler stream, reviewed eframe source and window-event evidence.

The [foreground keyboard launch](rust/rw02-instance.md#second-launch-from-a-foreground-test-window)
uses the same retained executable on a newly created input desktop. It
starts the secondary from the test window's native key handler and records
the focus of the original primary. Run it after the ordinary retained
launcher and the resource measurements.

The native feasibility workflow runs the Windows storage recovery trial after
the watch tests. Its `rust-recovery-<target>-<commit>` artifact contains the
complete evidence inventory for both path comparison modes, including VHD
cleanup. After the eight recovery cases the same job selects the reviewed
`--windows-provider` trial. It reads and renames a new 45-byte file on the
second private FAT volume. Check the recovery status, the separate
`windows-provider.json` and the final VHD readback. The command fails if
either selected check fails or the host cannot supply the provider.
[Windows recovery and provider fixture](rust/rw02-storage-faults.md).
The desktop assessment retains early Windows writer and tray results
before the scan. Its final artifact includes the desktop logs and Linux
storage recovery evidence. Each archive name includes the target and commit.
After the GUI build and YAML reconstruction, the Windows job exercises
ordinary launches on its private desktop without a notification area and on
the disposable input desktop with a separate synthetic profile. Both paths
launch the same GUI executable a second time without arguments. The results and process logs
are available in `rust-launcher-<target>-<commit>` as soon as that step
finishes, and under `windows-launcher/<target>/` in the final desktop archive.
[Windows launcher procedure](rust/rw02-instance.md#ordinary-second-launch-of-the-windows-gui).
The Windows recorder retains the measured job's CPU ticks and the working-set
bytes of its live members. Replay these samples with the three completed WPF
trials when comparing resources on a new machine.
[Job accounting and child-lifetime test](rust/rw02-windows-window.md#process-accounting-for-the-same-host-wpf-budget).
The Windows desktop job first records the WPF budget and the regular Mailbox
and FIFO trials. Its subsequent `--dispatch` trace compares both retained
window wake paths and the original hidden-paint policy with the same executable,
host and budget. Results and per-trial logs appear under
`windows-warm-window/<target>/dispatch/`. Preserve the adjacent
`eframe-source.zip` with the native build receipt and `compiler.jsonl` for
offline reproduction. The archive contains the original eframe and winit
crates, licenses and changes. The retained launcher verifies both local
library outputs against the actual native Cargo stream before starting the GUI.
See the [window measurements](rust/rw02-windows-window.md).
The [Windows x64 frame observer](../tools/rust-qa/windows-frame-cost/README.md)
pairs an instrumented inventory scan with the ordinary window measurement.
After that scan, the optional `--deferred-frame` trial measures a separately
compiled x64 CPU-adapter GUI. Its readback pairs a resumed redraw with
a successful presentation while the reopened window was visible. The
ordinary three-trial run still owns the resource decision.
[Deferred-frame commands and evidence](../tools/rust-qa/windows-frame-cost/README.md#deferred-readiness-on-the-windows-x64-cpu-adapter).
The WPF recorder queries the shipping tray icon after each idle trial and
retains the HRESULT and rectangle with the receiver identity.
[Shipping tray lookup](rust/rw02-windows-services.md#shipping-wpf-tray-lookup).

After the regular retained-window trials have produced their report, use
`python -B tools/rust-qa/windows-gdi-control/assess.py $env:NATIVE_TARGET`
from the native MSVC environment on that runner to compare GDI with WPF
and eframe. The result includes four visibility timings, verified changes
to two screen pixels and matching kernel file events during the
100,000-file scan. [GDI recorder and artifacts](../tools/rust-qa/windows-gdi-control/README.md).

On the same native Windows x64 runner,
`python tools/rust-qa/windows-warm-window/measure.py x86_64-pc-windows-msvc --gdi-present`
compares the full retained egui view drawing offscreen and presenting through
GDI. It uses the earlier WPF limits, records the actual bitmap transfers,
and verifies edits in the reopened filename field.
[Full-view renderer and offline replay](../tools/rust-qa/windows-gdi-present/README.md).

The x64 and ARM64 import-library jobs rebuild the selected native library
and exercise its respective winit or transport consumer. [Import-library reconstruction](rust/rw02-windows-imports.md).

The [crash and storage exhaustion fixture](rust/rw02-storage-faults.md)
uses separate copies for both language verifiers and preserves each
original backup. The four native desktop jobs select `--stored-keys` in the
SQLite assessment. Each job records the C# writer's complete casing table,
the two synthetic backups and the Rust observations for entries, tombstones
and repair journals. Inspect `stored-keys/result.json` and the original
`casing-fixtures/` inside the native storage evidence. [Cross-profile storage results](rust/rw02-legacy.md#stored-sqlite-identities-across-two-casing-profiles).
The same command inserts a new row on a copy of each backup, then uses the
original C# store for two successive upserts. The top-level `result.json`
records their readback under `storedKeys.newEntries`.
[Native write and readback](rust/rw02-legacy.md#native-shipping-upserts-after-a-concordant-rust-insert).
On Linux the fault fixture's private mount requires the documented
namespace launcher. The [combined profile](rust/rw02-combined-profile.md)
builds from verified local archives and exercises an offline Linux relink.
Each successful native build also generates a target-specific SPDX inventory.
The [SBOM commands](rust/rw02-combined-sbom.md) reproduce it from the native
run directory or an archived run with its published SHA-256. The desktop
workflow also selects the [native notice archive](rust/rw02-combined-notices.md).
It retains the locked original crates in the project cache, builds offline,
and uploads the native compiler receipt and its indexed outputs together as
`rust-native-input-<target>-<commit>.zip`. The notice generator verifies this
ZIP against the SHA-256 returned by Actions. After readback succeeds the job
retains `rust-notices-<target>-<commit>.zip` for that development executable.
`python3 -B tools/rust-qa/native-notice-input.py cache` checks the existing
cache offline. `cache --fetch-missing` acquires a missing pinned input.
The [appearance observer](rust/rw02-appearance.md) reads actual pixels after
portal changes and the [Plasma fixture](rust/rw02-plasma.md) activates the
visible branded panel icon on a native x64 or ARM64 Ubuntu guest. Each
architecture has a package inventory verified against Ubuntu's signed
indexes. The individual guides list native prerequisites and output directories.

On the disposable Windows rewrite runner, `python3 -B tools/rust-qa/appearance/windows.py "$NATIVE_TARGET"`
measures the ordinary Rust window before, during and after a temporary change
of the session's [high contrast mode](rust/rw02-appearance.md#windows-contrast-theme-observation).

The [GNOME input and scale fixture](rust/rw02-wayland-input.md) uses a private
Shell and separate compositor/client traces. Fedora uses IBus Anthy by
default. Ubuntu Noble uses `--ibus-engine mozc`. The [graphics recovery
fixture](rust/rw02-graphics.md) records presentation and input across device
replacement. The [text editing fixture](rust/rw02-font-coverage.md) compares
the released and corrected mixed-direction caret against actual rendered glyphs.

The [Windows IME assessment](rust/rw02-windows-ime.md) requires a native
input service and an owned foreground filename field. Its hosted wrapper
records missing components and verifies the disposable account's cleanup.
The [ordinary Windows filename checks](rust/rw02-windows-text.md) run against
the same native GUI and verify glyph coverage, cursor movement and selection.
The [native Windows display check](rust/rw02-windows-display.md) records the
current WTS transport and monitor DPI. On a disposable VM use `--retained`
to measure the paired Windows executable and require actual mixed-DPI or RDP
rendering. The [Ubuntu Orca check](rust/rw02-ubuntu-reader.md)
uses a private audio sink and verifies announcements on X11 and Wayland.

The [activation fixture](rust/rw02-instance.md) links the actual shipping coordinator
and exercises both protocol directions and file guard ownership in separate processes.
Windows runs it only on the disposable rewrite runner because the legacy names contain the actual account SID.

The [YAML assessment](rust/rw02-yaml.md#reading-the-original-yaml-file-bytes)
moves its byte-preserving synthetic reference before Rust reads it, then opens
the Rust-written files with the shipping C# loader. Each successful native
round trip publishes its individual run directory in the source-revision
`rust-yaml-<target>-<commit>` Actions artifact. It includes the original
files, [100- and 300-folder comparisons](rust/rw02-yaml.md#ordinary-profiles-with-100-and-300-folders)
and [shipping saves with Unicode line and paragraph separators](rust/rw02-yaml.md#physical-unicode-breaks-in-shipping-saves). The separate private cache
contains original third-party archives. The [Linux service tests](rust/rw02-linux-services.md)
exercise tray-owner changes and actual synthetic Documents grants. On a native
Linux builder, set `IFW_QA_REFERENCE_SDK` to the root of the pinned .NET SDK
and `IFW_QA_REFERENCE_PACKAGES` to a populated NuGet cache below `artifacts/`.
The grant oracle mounts both read-only and restores offline. The hosted job
populates this package cache while building the earlier storage and YAML oracles.
The
[portal comparison builder](rust/rw02-portal-upstream.md) replays one upstream
fix on exact release sources in an offline SDK. It writes the executable to
the ignored test area for the private namespace. The [Noble comparison](rust/rw02-portal-noble.md)
exercises the packaged Ubuntu daemon, a pristine Ubuntu rebuild and the
backport with both the C# and Rust readers in the same run. The separate
[Noble package installation and rollback](../tools/rust-qa/portal-noble/installed/README.md)
uses offline KVM guests and a regular user's installed Flatpak. The
[Windows service tests](rust/rw02-windows-services.md) exercise per-user
shortcut registration, Shell notifications and independent UI Automation.
After the native Shell build on a disposable target, run
`python3 -B tools/rust-qa/windows-services/activation.py "$NATIVE_TARGET"`
to exercise the private Explorer taskbar and retain its activation receipt.
The same job later runs
`python -B tools/rust-qa/windows-services/notification.py <native-target>`
using its earlier native service build. The readback records Shell policy,
the request status, the matching balloon callback, and independent
on-screen evidence of the synthetic title and body. The per-target output
is in `rust-notification-<target>-<commit>`.
[Notification observation](rust/rw02-windows-services.md#late-notification-on-the-original-desktop).
After those measurements, the same native Windows service binary sends two
WinRT notifications under a unique test shortcut. The history recorder reads
both from separate processes and verifies removal by tag and group. The
`rust-toast-history-<target>-<commit>` archive records Windows' response.
[Command and replay](../tools/rust-qa/windows-services/toast-history.md).
The integrated graphics and Windows scan fixtures use the same
[reviewed worker sources](../tools/rust-qa/performance/worker-inputs.json).
Update these hashes after reviewing changes to the inventory or its filesystem
adapter. The historical comparison uses its original source receipts.
The [native folder chooser fixture](rust/rw02-portal-dialog.md) exercises
X11 and Wayland parents, selection and denial. The local Flatpak variant
installs an isolated test app in a temporary repository. The GNOME variant
checks its on-screen notification and autostart registration and removal.
On older host portals, `--host-chooser-only` exercises the parented picker
without app-ID registration. The disposable Ubuntu job obtains a verified
runtime once and uses `--flatpak --hosted-runtime` for attributed app actions.

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

### Rust foundation CodeQL

The rewrite draft PR runs the Rust security-extended suite on the five-crate
workspace under `rust/`. A fresh Git archive binds each scan to the PR head.
Two Linux-hosted jobs select the Linux and Windows x64 compiler configurations.
Each compares every extracted Rust file with its original Git blob and checks
which files have semantic information for that target. The standalone GUI and
QA probes under `tools/rust-qa/` are outside this scan. Platform runtime and
filesystem evidence comes from the native assessment workflows.
[Workflow](../.github/workflows/rust-codeql.yaml) · [Native evidence](rust/acceptance.md#native-evidence-matrix).

CodeQL CLI 2.27.5 uses the MIT-licensed `rust-queries` 0.1.47 and
`rust-all` 0.2.26 packs. The development-only CLI license permits automated
analysis of this public open-source repository on GitHub. Its Rust extractor
selects 1.99.0. The workspace builds with the compiler in
`rust/rust-toolchain.toml`. Each Actions artifact contains the SARIF results,
extractor log, semantic coverage and a summary with source hashes and reported
alerts. Incomplete coverage, a CodeQL database quality warning, a reported
security alert or an analysis error fails the check. These jobs use a read-only
repository token and retain the artifacts for 14 days. GitHub's existing default code scanning operates
independently. [CLI terms](https://github.com/github/codeql-cli-binaries/blob/v2.27.5/LICENSE.md)
· [Query license](https://github.com/github/codeql/blob/codeql-cli/v2.27.5/LICENSE)
· [Extractor toolchain](https://github.com/github/codeql/blob/codeql-cli/v2.27.5/rust/extractor/src/toolchain.rs).

To reproduce a scan on Linux x64, download the official `codeql-bundle-linux64.tar.zst`.
Use an isolated Rustup environment with 1.99.0, `rust-src` and the selected
target installed. Supply the bundle path, target, fresh output directory and
full checkout revision. The script checks the bundle's SHA-256 before
unpacking it. Cargo operates offline during extraction.
[Official bundle](https://github.com/github/codeql-action/releases/tag/codeql-bundle-v2.27.5) · [Analysis script](../tools/codeql-rust/scan.sh).

```bash
bash tools/codeql-rust/scan.sh /tmp/codeql-bundle-linux64.tar.zst x86_64-pc-windows-msvc /tmp/ifw-codeql-windows "$(git rev-parse HEAD)"
```

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

The rewrite configuration adds the same weekly schedule for Cargo in
`/rust`, targeting `rewrite/rust` for version updates. The five current
workspace members have no external Cargo dependencies. Source-frozen
development oracles under `tools/rust-qa` have their own reviewed input
pins. For each product dependency update, check the exact sources,
licenses, features, native inputs and offline lockfile before merging.
GitHub reads the configuration from the default branch, so this rewrite-only
addition has no hosted schedule until a separately selected integration.
The target-branch option applies to version updates. [GitHub configuration
reference](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file#target-branch).

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
