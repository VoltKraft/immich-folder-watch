# Full Rust rewrite: repository assessment and migration plan

Assessment date: **2026-11-14**, Europe/Berlin.
Inspected baseline: **`19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`**, local `main`,
initially clean; product **3.0.4**, .NET SDK **10.0.401** pinned with roll-forward
disabled. Local origin tracking matched HEAD; no remote fetch or new verification
of historical release/catalog status was needed for this analysis.

**Scope: analysis and proposed design only.** No application, database, dependency,
workflow or installed system is changed. No Rust prototype was built and no
personal media/Immich service was accessed. The user selected the intended Rust
direction but explicitly deferred implementation. Future stages below require
implementation selection; their presence is not authorization to execute them.

The [project brief](project.md) owns requirements/selection and [status](status.md)
owns completion evidence. [Rust Desktop Standard](rust-desktop-standard.md) defines
the proposed reusable rules; this document owns the detailed product mapping,
technology rationale, migration risks and stage acceptance.

## Recommendation

Proceed with a staged replacement, preserving the existing .NET application as
the behavioral reference until all replacement gates pass. Recommend **egui/eframe
as the first GUI candidate**, not as an unconditional long-term commitment.
Keep it behind a presentation boundary so a future GUI change does not rewrite
synchronization, storage or native integration again.

Retain SQLite and existing YAML/configuration identities. Use a single per-user
Rust process with a supervised engine, native platform adapters and a dedicated
safe-filesystem boundary. No C# interoperability layer is required in the final
application. Existing C# code/tests remain development oracles during migration.

The user explicitly confirmed that “100% Rust” covers first-party application
code including GUI; native libraries and SQLite are allowed. This permits
rusqlite and OS bindings without pretending that GPU drivers, the OS or SQLite
are written in Rust. No JavaScript/WebView application runtime is proposed.

## Existing repository: what must be replaced and preserved

A mechanical inventory, excluding `bin/` and `obj/`, found 139 application C#
files (18,979 lines) and 65 test C# files (12,275 lines), excluding XAML, packaging
and other-language tests. These are scope indicators, not implementation estimates.
`FolderWatchWorker.cs` has 2,574 lines and `MainWindowViewModel.cs` 1,481; reproduce
their behavior in smaller state machines/use cases, not a line-by-line monolith.

| Existing area | Observed responsibility | Rust destination |
| --- | --- | --- |
| `src/ImmichFolderWatch.Core` | Config, worker, filtering, ordering, readiness, durable state, safe filesystem and platform interfaces | Domain/application, compatibility/storage, safe-filesystem and desktop contracts |
| `src/ImmichFolderWatch.Immich` | HTTP routes/fallbacks, uploads/downloads, exact-ID album mutations, bounded Socket.IO transport | Separate `ifw-immich` adapter |
| `src/ImmichFolderWatch.App.Shared` | Configuration draft/apply, status, navigation, English/German localization | Product application presentation state and egui views |
| `src/ImmichFolderWatch.App` | WPF, Windows tray/IPC/autostart/logging | Rust composition root plus Windows adapter |
| `src/ImmichFolderWatch.App.Linux` | Avalonia, portal grants, D-Bus tray, notifications, single-instance coordination | Same Rust GUI plus Linux adapter |
| Three test projects and `tools/tests` | Core, security, GUI/protocol and installer/workflow regressions | Compatibility fixtures plus Rust/native/package suites |
| `packaging/` and `.github/workflows/` | Four artifacts, upgrade checks, offline Flatpak, signed Pages, WinGet/Flathub | Preserve delivery contracts; replace runtime/build inputs in later stages |

Source anchors: [current architecture](architecture.md), [configuration contract](configuration.md),
[desktop guide](user-interface.md), [development workflow](development.md),
[watch-root security](watch-root-security.md) and [remediation record](security-remediation-20261109.md).
Current code supersedes stale summaries: some documentation calls Flatpak tray
disabled although `StatusNotifierItem` is wired; a brief SDK summary also lagged
behind `global.json`. These discrepancies are not permission to omit capabilities.

### Product parity matrix

Each row becomes fixture/test IDs during RW-01. An unchecked row blocks cutover.

| ID | Contract | Representative acceptance |
| --- | --- | --- |
| PAR-01 | Multiple sources; `uploadNew`, `uploadAll`, bidirectional `sync`; defaults and legacy config fallback | Startup/added-file behavior matches C# per mode; unknown legacy mode remains safely normalized |
| PAR-02 | Named-album flat sync or subfolders-as-albums, including unassigned root media | Exact membership, duplicate-name handling, remote trash, local deletion and guarded rename scenarios |
| PAR-03 | Recursion, per-source extension/exclusion filters, legacy global extensions, readiness, batching, retries, transfer order | First attempts before retries; stable order; in-progress transfers not interrupted for reordering |
| PAR-04 | Fast metadata reconciliation, tombstones, timestamp repairs, monotonic Last Sync | No upload/hash/download for unchanged files; replay after crashes preserves state/history |
| PAR-05 | HTTPS default, explicit insecure HTTP, permissions check, routes/fallbacks, Socket.IO plus polling | Mock server asserts requests, no redirect credential leakage, bounded incomplete results cannot delete |
| PAR-06 | Overview/Folders/Connection/Settings, folder editor, logs, drafts, Save and Apply, status/error/progress, update link | Keyboard and GUI flows; failed validation does not write; applied restart failures are explicit |
| PAR-07 | English/German, OS detection/live switching, theme, DPI, path display versus portal identity | Translated labels/menus, long paths, Unicode input, scaling and accessibility evidence |
| PAR-08 | Per-user locations, single instance, background/tray, autostart, CLI, native log targets | Old/new versions cannot both synchronize; window close and Quit remain different |
| PAR-09 | Windows MSI x64/ARM64; Flatpak x86_64/aarch64; signed Pages; catalog metadata | Real old-to-new install/update/uninstall preserves data and permissions; all four assets match one revision |
| PAR-10 | Native notifications requested for the new standard | Explicit event policy and platform tests; do not claim an already equivalent Windows notification implementation |

Notifications need a defined product policy: actionable persistent failure,
permission loss and user-requested completion events; rate-limit repeated offline
errors and avoid per-file notification storms. Current Linux notifier/protocol
coverage is not proof of user-visible cross-platform notifications. Do not put
API keys or private filenames in notification bodies by default.

## GUI decision

Primary sources were checked on the assessment date. Versions below are research
snapshots, **not new dependency pins or an audited complete Cargo graph**.

| Candidate | Strength for this product | Limitations and decision |
| --- | --- | --- |
| **egui/eframe 0.37.0** | Rust-authored GUI, compact immediate-mode presentation, winit/native windows, wgpu/glow integration; suitable for settings/status/log views; AccessKit integration | Custom-drawn controls; API evolution and integration work remain. Preferred candidate, gated by lifecycle, accessibility, rendering and license tests |
| **iced 0.14.0** | Rust-authored declarative UI; application/daemon model and software-renderer option | Credible alternative if eframe lifecycle/rendering fails. Stable native accessibility evidence is weaker; cannot assume it solves every egui limitation |
| **Slint 1.18.1** | Desktop controls, accessibility, tray and software rendering options | Normal UI authoring uses `.slint` DSL, conflicting with the selected Rust-source GUI preference. License/backend choices need specific review; GPLv3 is not automatically AGPLv3-incompatible. Not the selected default |

Do not select Tauri/Electron or a browser-based Rust UI: that conflicts with the
explicit no-WebView requirement. Rust bindings to a native toolkit can satisfy
the clarified first-party language boundary. GTK/Qt are non-preferred here because
they introduce another toolkit/distribution contract; they are not excluded merely
for calling native libraries.

egui is a good fit **for this application's comparatively compact desktop UI**.
It is not proven the best general-purpose GUI for every future desktop project.
The durable standard should be lifecycle, ports, security, persistence and
distribution; egui remains the default adapter. Treat its pre-1.0 API changes as
maintenance work, with pinned versions and reviewed coordinated updates.
The assessed egui/eframe 0.37.0 requires Rust 1.95; freeze an exact reviewed stable
toolchain meeting that and the resolved graph's other requirements in RW-02.

Prefer wgpu initially. Assess actual adapter selection and device-loss behavior
on Windows/Linux x64/ARM64, virtual machines, RDP and lower-end GPUs. `glow` is
a separately tested fallback candidate, not an automatic software-rendering
guarantee. Do not promise lower RAM/startup/idle CPU than .NET before measurement.
egui 0.37's `App::logic` can process wakeups while hidden; synchronization must
still run independently of UI logic/frame callbacks.

### Font and feature decision

The main egui code is MIT OR Apache-2.0, but the exact 0.37.0
`epaint_default_fonts` manifest declares
`(MIT OR Apache-2.0) AND OFL-1.1 AND Ubuntu-font-1.0`. The default assets include
Ubuntu/Hack/icon font notices. A top-level license badge is insufficient.

Proposed shipping profile: disable default features, explicitly select the native
renderer/window/accessibility features, **omit `default_fonts` and optional bundled
emoji fonts**, and embed separately reviewed fonts with their exact source,
license, notices and coverage tests. Do not introduce an unreviewed font package
by naming a font family alone. Cargo feature unification must not re-enable the
default font package through another dependency. This design avoids depending on
an unresolved blanket judgment about the Ubuntu font license.

Disable the optional eframe `inspection` feature in production: it can expose
remote UI inspection/control when configured. Test builds may use isolated
instrumentation after its network scope is reviewed. No debug-control server is
part of a release.

### GUI acceptance before full commitment

RW-02 must demonstrate: hidden startup; close/reopen without engine stop;
tray/launcher activation without a visible window; clean Quit/restart; no busy
repaint loop; Wayland and X11; Windows focus/COM rules; portal parenting;
tray-host absence/restart; native notifications; scaling, multi-monitor and
keyboard-only flows; screen-reader labels/focus on Windows and Linux; password
masking; German text and IME/composition/Unicode paste; GPU initialization and
loss/fallback. UI automation and screenshots alone do not establish screen-reader
or real desktop acceptance.

Use the existing .NET app on the same machine/scenario as the performance baseline.
Record startup, idle/hidden CPU, memory, repaint frequency and response during a
synthetic 100,000-file scan; choose explicit budgets from those measurements
before approving the GUI. A failed essential gate triggers a focused iced
comparison or a documented eframe integration fix, not a silent feature reduction.

## Technology choices and license checkpoints

| Area | Proposed choice / observed version | Decision and remaining evidence |
| --- | --- | --- |
| Runtime | Tokio; observed upstream manifest 1.54.1, MIT | One supervised runtime, bounded queues; pin release/toolchain only at implementation selection |
| HTTP | reqwest 0.13.5, MIT OR Apache-2.0, with rustls | Explicit no-redirect policy; stream limits, proxy/certificate-store parity and timeouts; inspect crypto/native dependencies |
| Persistence | rusqlite 0.42.0, MIT; SQLite public domain | Dedicated worker, transactions/backup; prefer reviewed bundled SQLite for consistent packaged behavior; no SQLCipher or extension loading by default |
| YAML | serde plus serde-saphyr 2.1.1 candidate, MIT OR Apache-2.0 | Current maintained candidate, not a proven YamlDotNet replacement. Golden scalar/default/alias tests; no includes/properties/interpolation; bounded diagnostics with secret redaction |
| Watching | notify 8.2.2, CC0-1.0; supporting notify crates have their own licenses | Events are hints; bounded debounce and authorized rescan. Preserve periodic polling for portal/FUSE and overflow recovery |
| Linux desktop | ashpd 0.14.0 / zbus 6.3.0, MIT | FileChooser/Documents/Background/Notification/Settings adapters; preserve grants and denied/unavailable states |
| Tray | tray-icon 0.26.1, MIT OR Apache-2.0 | Windows native backend; Linux explicit KSNI backend or direct audited D-Bus adapter. Default GTK/AppIndicator profile is not selected implicitly |
| Windows | windows 0.62.2, MIT OR Apache-2.0 | Native shell/COM, per-user IPC, tray/logging; safe wrappers and ABI/native tests |
| Realtime | Dedicated Immich Socket.IO/Engine.IO adapter | `rust_socketio` 0.6.0 is an evaluation candidate, not accepted. Verify transport injection, origin/redirect controls, bounded frames and reconnect cancellation before selecting/forking it |
| Logging/errors | tracing and typed errors, behind product redaction policy | Exact versions/licenses/transitives to be frozen in RW-02; preserve Event Log/journald/file choices |

The assessed tray KSNI graph uses zbus 5 through ksni, while ashpd uses zbus 6.
Do not claim one shared connection/runtime automatically. Test the complete
feature graph; either accept documented separate versions/connections or implement
the small SNI/DBusMenu surface on the chosen D-Bus layer. Linux tray ownership
must fit the existing app's filtered D-Bus namespace, including watcher recovery.

Realtime is a feasibility gate because WebSocket alone is not Socket.IO. Retain
handshake/authentication, Engine.IO framing/heartbeat, polling/upgrade behavior,
event names, bounded reconnect and polling fallback. A maintained reviewed fork
or a narrowly implemented adapter is preferable to a library that cannot enforce
the security contract; size that work in RW-02. Polling-only is not full parity.

All dependency/license statements are preliminary source evidence. No packages
were added or downloaded into a new build. Final AGPL-3.0-only acceptance requires
the resolved target/feature graph, native/assets inventory, notices and corresponding
source. See [RDS-07](rust-desktop-standard.md#rds-07-dependencies-and-licensing).

## Target architecture and project structure

Initially keep the Rust workspace under `rust/` alongside the stable .NET sources.
This prevents an incomplete engine from replacing production build entry points.
The following is a **proposed layout**, not created scaffolding:

```text
rust/
  Cargo.toml                 # workspace, dependency/features policy
  Cargo.lock                 # committed application resolution
  rust-toolchain.toml        # exact reviewed stable compiler
  crates/
    desktop-contracts/      # identity, platform capabilities, lifecycle messages
    desktop-runtime/        # supervision, channels, cancellation, redacted logging
    desktop-platform/       # Windows/Linux modules; no Immich semantics
    desktop-ui-egui/        # reusable shell/theme/widgets, no sync/network/SQL
    safe-fs/                # retained capabilities and native security boundary
    ifw-domain/             # modes, identities, operation decisions, invariants
    ifw-application/        # sync state machines, reconciliation, config apply
    ifw-immich/             # HTTP + Socket.IO + API compatibility
    ifw-persistence/        # SQLite actor, legacy schema/YAML codecs, migration
  apps/
    immich-folder-watch/    # product egui views + composition root + CLI
  xtask/                    # build/branding/package/fixture orchestration
  tests/fixtures/           # synthetic legacy/config/protocol scenarios
  fuzz/                     # bounded parser and state-transition targets
packaging/                  # preserve MSI/Flatpak identities and trust contracts
docs/                       # contracts, ADRs, stage evidence, migration handbook
```

Logical boundaries matter more than crate count: start small, and keep a boundary
as a module until a separate crate measurably enforces security, dependency
direction or reuse. No general desktop framework or plugin API is required.
`ifw-persistence` owns product-specific encodings, not the generic foundation.

Split the current worker into local observation, remote inventory, reconciliation
planning, bounded transfer scheduling, execution and durable state transitions.
Planning is side-effect-free. Execution receives authorized capabilities plus a
complete inventory/operation decision; a filename or watcher event cannot authorize
deletion. Preserve startup recovery order before evaluating fresh uploads.

The UI sends commands and observes snapshots. One supervisor serializes apply,
restart and shutdown; a database worker performs synchronous SQLite operations.
Use an engine-generation token for late completions. Session ownership and all
file/root leases outlive outstanding operations. If safe shutdown cannot complete,
an installer must refuse removal; a timeout is not permission to start another engine.

Reusable parts are desktop lifecycle/platform APIs, safe persistence primitives,
logging, the reviewed filesystem boundary and build policy. Immich routes,
account hashing, source modes, album ownership, sync schema and deletion decisions
remain product code. Validate extraction through RDS-10's separate synthetic consumer.

## Data compatibility and migration

### Existing encodings are a contract

Keep `config.yaml`, `sync-state.db`, app/IPC identity and existing Windows/XDG/Flatpak
locations. Do not introduce TOML, a new keyring requirement, a new database engine
or a new stable Flatpak app ID during the rewrite. Preserve portal grant identity
separately from display paths; do not globally canonicalize paths or convert them
through lossy Unicode strings.

The database has `PRAGMA user_version = 1` and four tables:

| Table | Required preserved meaning |
| --- | --- |
| `sync_entries` | Account/source/path keys, asset/album mappings, size/mtime, numeric direction/status, tombstones and expiry |
| `owned_albums` | Exact-ID creation provenance; startup deliberately revokes mutation authority for the active account |
| `sync_timestamp_repairs` | Durable JSON original entry, desired timestamps and SHA-256; compare-and-swap recovery |
| `sync_account_status` | Monotonic last actual transfer, including one-time legacy backfill semantics |

Exact traps verified in the owning source:

- Account scope: lowercase SHA-256 of UTF-8
  `trimmedServerUrlWithoutTrailingSlash + "\n" + apiKey`; do not normalize URL
  case/default ports or trim the key differently. See
  [`SyncAccountScope.cs`](../src/ImmichFolderWatch.Core/Models/SyncAccountScope.cs).
- Windows keys use .NET invariant uppercase after path normalization; Linux
  keys retain case. Rust Unicode uppercase is not an assumed drop-in replacement.
  Preserve stored keys and test newly generated keys against the baseline, including
  Unicode, UNC and root/trailing-separator cases. See
  [`SqliteSyncStateStore.cs`](../src/ImmichFolderWatch.Core/Services/SqliteSyncStateStore.cs).
- SQL timestamp text uses UTC `.NET "O"`: seven fractional digits and `+00:00`.
  `MAX()` relies on compatible ordering. Variable-precision RFC3339 or `Z` must
  not replace it accidentally. Timestamp precision/recovery uses filesystem readback.
- Repair JSON uses PascalCase properties and numeric enums; preserve its codec.
  Mapping update and journal removal share a transaction. See
  [`SyncTimestampRepair.cs`](../src/ImmichFolderWatch.Core/Models/SyncTimestampRepair.cs).
- Legacy `deviceAssetId` hashes display path, size, .NET ticks and uppercase content
  digest, then lowercases the final SHA-256. Digest and upload must use the same
  opened media handle. See
  [`ImmichAssetClient.cs`](../src/ImmichFolderWatch.Immich/ImmichAssetClient.cs).
- Current tombstone lifetime is 120 seconds. Preserve expiry/restart behavior.
  Schema v0/older optional-table combinations need fixture coverage; unknown future
  versions must be rejected without mutation.

Preserving `owned_albums` data does **not** mean restoring stale authorization:
the C# worker intentionally revokes it at startup. A successful byte-for-byte
migration that re-enables old destructive authority would be a security regression.

### Cutover protocol

1. Build synthetic fixtures from the exact C# baseline in RW-01: YAML-sensitive
   strings (`null`, numeric-looking names, backslashes), legacy defaults, all
   tables, timestamps, tombstones, Unicode keys and incomplete repair journals.
   Never put a real API key or user's database in fixtures.
2. Prove Rust-read/C#-write and C#-read/Rust-write compatibility in isolated profiles.
   Candidates use disposable data and synthetic media; do not run both engines
   against the same live folders, server or database, even in separate install paths.
3. At actual cutover, stop and verify the old engine; acquire the same per-user
   single-instance ownership before any state writes. Windows uses
   `Local\ImmichFolderWatch-{SID}` and `ifw-{SID}` with `SHOW_GUI`; Linux uses
   `immich-folder-watch.sock` and the existing private runtime path. The new version
   must recognize the old process and safely request activation/refuse a second engine.
   The Windows `Local\` mutex is session-scoped, so it is insufficient for exclusive
   ownership across console/RDP sessions with the same SID. Establish a separate
   cross-session per-user writer guard for Rust. Legacy versions do not honor a new
   guard: prove all legacy instances are stopped and prevent their re-entry during
   the installation/ownership handover, or fail closed. Test same-SID, two-session
   old/new combinations; do not treat an activation response as a writer lock.
4. Produce a permission-protected consistent SQLite backup, including committed
   WAL state, via the backup API after quiescing the engine. Save config and migration
   manifest with hashes. Do not copy only a live `.db` or delete recovery sidecars.
5. Inspect schema/integrity and validate configuration without destructive side
   effects. Retain schema 1 and all compatible codecs for the first Rust release;
   avoid a schema conversion when none is needed. Any necessary change gets its own
   transactional migration and separately proven reverse-compatibility contract.
6. Follow the established order: initialize state; revoke stale album authority;
   restore history and expire tombstones; pin roots/register watchers/load state;
   recover timestamp journals; reconcile known files; pull remote state; reconcile
   unknown local files. The first migration validation may show
   a dry-run diff; it must not trigger bootstrap deletion just because a parser or
   identity differs. Unknown/inconsistent state blocks synchronization for review.
7. Verify unchanged fixtures require no transfers; explicitly enable normal sync
   only after migration validation succeeds. Preserve backups and journal evidence.
8. Test rollback after Rust has uploaded, downloaded, deleted and repaired timestamps.
   Prefer the old compatible binary reading the latest valid state after exclusive
   ownership transfer. Restoring an old backup is a recovery operation, **not** a
   reversal of remote side effects; require reconciliation and suspend deletion
   until consistency is established. Never promise that MSI rollback undoes sync.

Current corruption quarantine/bootstrap behavior is a reference case; migration
must not classify a codec mismatch as corruption and silently create empty state.
Retain original files and distinguish unsupported formats from actual SQLite
corruption and from permission/space/I/O failures.

## Security and data-loss gates

The [existing filesystem contract](watch-root-security.md) remains the minimum.
Port behavior and adversarial tests before enabling destructive Rust operations.

| Boundary | Required Rust property / test |
| --- | --- |
| Root/parent/leaf identity | Retained no-follow handles for enumeration, reads, absence, retries and writes; ordinary-directory replacement as well as symlink/junction tests |
| Local delete after upload | Same successfully uploaded file object; verified identity; persisted size/mtime alone never authorizes cleanup; restart/retry reuploads before cleanup |
| Download staging | Protected transaction namespace, retained handle, atomic no-replace publication, safe cancellation and quarantine retention |
| Timestamp repair | Content verification, hard-link checks, compare-and-swap state, recoverable journal; outside sentinel bytes/metadata unchanged |
| Album changes | Exact created album ID and live provenance; no adoption by equal name; stale rights revoked on restart/ambiguous rename |
| Inventory | Failed/truncated/local-incomplete scans cannot authorize deletion; native watcher events are only rescan hints |
| Persistence | Write failure stops transfers; completion follows durable state; crash injection at every filesystem/API/DB boundary |
| Config/IPC | Private per-user ownership/permissions, bounded activation messages and no symlink fallback; secrets redacted |
| HTTP/realtime | HTTPS default, opt-in HTTP, certificate validation, no credentialed redirects, exact origin and bounded messages/reconnect |

Preserve the current transfer ceilings: metadata 16 MiB; diagnostic body 64 KiB;
aggregate search 128 MiB/125,000 assets/500 pages; download 100 GiB with 1 GiB
free-space reserve; 60-second inactivity and six-hour download deadline; realtime
messages 4 MiB. Apply limits while streaming and after decompression as applicable,
not only after allocation or by trusting `Content-Length`.

Linux implementation candidates are descriptor-relative native operations with
owner-only staging and atomic no-replace support. Windows requires retained
directory/file handles, relative opens, reparse checks and correct sharing/rename/
delete semantics. `std::fs`, path canonicalization, `notify`, or a capability crate
alone is not evidence of equivalence. Isolate and independently review unsafe/FFI.

Retain the documented per-user threat model and residuals: no defense against a
privileged actor or an equivalent process reading user credentials; hard-link
checks are observations; free-space checks do not reserve blocks; safe failed
restoration may retain quarantine contents. Never recursively “clean” reserved
`.ifw-internal-` directories without their proven ownership/identity contract.
Native ARM64/UNC and portal/FUSE evidence must be obtained, not inferred from x64.

## Native integration and distribution

Preserve Windows per-machine binaries with per-user config/state; autostart remains
a user Startup shortcut created through native shell APIs. Preserve CLI
`--autostart`, Linux `--background`, `--migrate-legacy-user` and legacy ProgramData migration. Linux keeps
portal-mediated folder access, persistent grants and Background portal autostart.
Denial is a normal UI state, not a reason to escape the sandbox.

Replace the Windows Event Log message resource/registration as well as the GUI:
the current installer references a .NET Framework `EventLogMessages.dll`. A Rust
runtime must not accidentally depend on that legacy resource. Preserve Event Log,
journald and file log semantics and default target selection.

| Build/test lane | Rust target | Candidate runner / required package |
| --- | --- | --- |
| Windows x64 | `x86_64-pc-windows-msvc` | Pinned Windows x64 image; x64 MSI and installed upgrade test |
| Windows ARM64 | `aarch64-pc-windows-msvc` | `windows-11-arm` availability/toolchain checked at execution; native tests and ARM64 MSI |
| Linux x64 | `x86_64-unknown-linux-gnu` | Pinned Ubuntu x64 plus exact Flatpak SDK/runtime/container; x86_64 bundle |
| Linux ARM64 | `aarch64-unknown-linux-gnu` | `ubuntu-24.04-arm` plus matching native Flatpak toolchain; aarch64 bundle |

These four triples are currently supported by Rust. GitHub documents the ARM
runner labels, but availability is not evidence that an interactive GPU/desktop
test passes there. Add real desktop/VM acceptance for Wayland/X11, GNOME/KDE,
Windows sessions, RDP and ARM64. If a native lane cannot execute required checks,
record the missing evidence and block that release gate; do not label cross-builds
as runtime acceptance.

Pull requests run format/Clippy, domain/compatibility/security tests, Rust CodeQL,
dependency/license/source checks and candidate packaging with no publication
credentials. Keep .NET tests while they still supply the oracle. Add Cargo
Dependabot coverage when the workspace exists; retain manual reviewed merges.

Generate exact Cargo vendor/offline sources and compiler/native-tool inputs for
both Flatpak architectures; verify reconstruction without network access. Retain
the Flatpak app ID/branch and GPG identity. Wayland support is an explicit new
desktop acceptance row; do not widen filesystem or D-Bus permissions to make a
candidate work. Flathub requires its source manifest/dependency inputs, not only
an upstream bundle or updated tag.

Preserve MSI product/upgrade-family identities and architecture separation. Keep
close-or-abort before removal, removal inside rollback, compiled-MSI contract
checks, and real upgrades while the old .NET process is running. Test both
architectures, data preservation, no-runtime-required startup, uninstall, repair,
reboot-required outcomes and cross-user process handling. No automatic shutdown
claim is inherited from the historical safe-refusal-plus-retry test.

Publication remains all four verified artifacts from one immutable revision.
Build jobs remain read-only; signing/publishing and downstream dispatch stay
separate. Candidate builds never feed stable Pages. WinGet/Flathub submission is
distinct from external acceptance. Preserve existing release assets/tags.

Keep `<Version>` authoritative during the coexistence period. At cutover, move
version ownership deliberately to workspace metadata and validate all MSI,
AppStream, binary and manifest versions from that one source. A language rewrite
alone does not determine a SemVer major bump; evaluate actual public compatibility
at release selection. No version bump, prerelease pipeline change or release is
selected by this plan.

## Staged implementation proposal

Only **RW-00** is selected now. Later stages are proposed, ordered work packages;
completion of this document does not start RW-01. The current product remains
maintained and releasable throughout the migration. Track fixes made to the .NET
baseline after RW-01 in the parity corpus before cutting over.

| Stage | Deliverable and dependency | Exit evidence / stop condition |
| --- | --- | --- |
| **RW-00 — assessment** | This plan, reusable standard, brief/status links | Repository/primary-source review, explicit scope, reviewed docs; no implementation |
| **RW-01 — freeze compatibility** | Selected implementation scope; inventory PAR-01…10; synthetic YAML/SQLite/API/lifecycle fixtures and baseline runs | Fixture provenance and expected results from C#; every public feature/security rule mapped; no real-user data |
| **RW-02 — prove feasibility** | Minimal Rust GUI/native integration, licensed font/feature graph, filesystem primitive spike, legacy codec and realtime transport spikes; depends on RW-01 | Four-target native results; GUI gates pass; exact license graph; no impossible FS/realtime requirement hidden; choose/freeze stack and effort estimate |
| **RW-03 — foundation and storage** | Workspace boundaries, supervisor, desktop adapters, safe-fs, config/SQLite compatibility and backup tooling; depends on RW-02 | Cross-language read/write fixtures; single-instance interop including cross-session exclusion; crash recovery and independently reviewed adversarial filesystem tests |
| **RW-04 — upload engine** | API adapter, all upload modes, filters, readiness, ordering, retries, permissions, durable history; depends on RW-03 | Fake-server differential traces; verified cleanup only after security gates; crash/no-op-restart/changed-file scenarios |
| **RW-05 — bidirectional engine** | Downloads, membership, unassigned media, realtime/polling, tombstones, album ownership, renames and timestamp repairs; depends on RW-04 | Complete/truncated inventory tests; all deletion/race/crash gates; deterministic parity against C# across modes |
| **RW-06 — complete UI and reuse** | All existing GUI flows/localization/status; notifications policy; second isolated foundation consumer; uses RW-03 interfaces and finishes after RW-05 | PAR-06…08/10 and real accessibility/desktop performance gates; second app imports no Immich code; screenshot and keyboard evidence |
| **RW-07 — package and migration rehearsal** | Four packages, offline reconstruction, native upgrade/rollback rehearsals, license/SBOM/source artifacts; depends on RW-05/06 | Old .NET → Rust → compatible rollback after activity, same-SID two-session handover, clean-install/repair/uninstall and sandbox evidence; independent security review |
| **RW-08 — selected release and retirement** | Separate publication selection after RW-07; final docs/version ownership, production Rust builds; remove active .NET app dependencies only after acceptance | Exact-revision CI plus actual installed-package acceptance; publish under authorized release workflow; preserve history/oracles/recovery documentation |

GUI completion and packaging preparation can proceed in parallel after interfaces
stabilize, but cannot bypass secure-filesystem or data-compatibility gates. A pilot
against disposable data precedes any separately authorized real-user migration.
No calendar estimate is claimed before RW-02 exposes the native/realtime costs;
security, parity and recovery are the dominant work, not drawing the settings UI.

## Principal risks and decisions still to validate

| Risk | Impact | Mitigation / owning stage |
| --- | --- | --- |
| Incorrect deletion/recovery semantics | Irreversible local loss or unexpected remote trash | Freeze corpus; capabilities; fault injection; independent review, RW-01/03/05 |
| Codec/key/timestamp drift | Full reupload, lost mapping or bad Last Sync | Exact legacy codecs and two-way fixtures, RW-01/03 |
| Concurrent old/new instances | Conflicting remote changes despite SQLite locking | Existing IPC/ownership interop and staged exclusive cutover, RW-02/03/07 |
| eframe lifecycle/accessibility/GPU gaps | Inaccessible or unreachable background app | Native spike and measured acceptance; iced fallback review, RW-02/06 |
| Native API/ARM64/UNC/FUSE differences | Works in CI but unsafe or unusable on actual systems | Native adversarial/package/desktop tests, RW-02/03/07 |
| Cargo feature/asset/license surprises | AGPL-incompatible distribution | Font defaults disabled, exact graph and artifact inventory, RW-02/07 |
| Socket.IO library cannot enforce current policy | Credential leak, unbounded memory or stale reconnect | Early transport audit/protocol tests; reviewed fork/adapter if necessary, RW-02/05 |
| Baseline evolves during long rewrite | Newly fixed C# defects reappear in Rust | Maintain fixture/change ledger and refresh baseline before cutover, every stage |
| Over-generalized framework | Delays parity and increases maintenance surface | Small ports, real second consumer, no public framework promise, RW-03/06 |
| Installer rollback confused with data rollback | Stale mappings after remote side effects | Compatible state and explicit recovery procedure, RW-07 |

No unresolved question prevents completing this analysis. Exact library pins,
renderer fallback, selected fonts, Socket.IO implementation and measured performance
budgets are engineering outcomes of RW-02. If a mandatory capability cannot be
met, revise the proposed design visibly rather than silently weakening parity.

## Primary-source research record

Checked 2026-11-14; links identify the evidence used, not a claim of executed
integration. Exact release sources take precedence over moving `latest` pages.

- egui/eframe: [0.37.0 source](https://github.com/emilk/egui/tree/0.37.0),
  [eframe features](https://github.com/emilk/egui/blob/0.37.0/crates/eframe/Cargo.toml),
  [App lifecycle](https://github.com/emilk/egui/blob/0.37.0/crates/eframe/src/epi.rs),
  [font license expression](https://github.com/emilk/egui/blob/0.37.0/crates/epaint_default_fonts/Cargo.toml).
- GUI alternatives: [iced 0.14.0](https://github.com/iced-rs/iced/tree/0.14.0),
  [iced accessibility tracking](https://github.com/iced-rs/iced/issues/552),
  [Slint 1.18.1](https://github.com/slint-ui/slint/tree/v1.18.1),
  [Slint licensing](https://slint.dev/license).
- Storage: [rusqlite v0.42.0 manifest](https://github.com/rusqlite/rusqlite/blob/v0.42.0/Cargo.toml),
  [SQLite copyright](https://sqlite.org/copyright.html),
  [SQLite backup API](https://sqlite.org/backup.html).
- Configuration/network/runtime: [serde-saphyr 2.1.1](https://docs.rs/serde-saphyr/2.1.1/serde_saphyr/),
  [serde-saphyr source manifest](https://github.com/bourumir-wyngs/serde-saphyr/blob/master/Cargo.toml),
  [reqwest v0.13.5 manifest](https://github.com/seanmonstar/reqwest/blob/v0.13.5/Cargo.toml),
  [redirect policy](https://docs.rs/reqwest/0.13.5/reqwest/redirect/struct.Policy.html),
  [rustls providers](https://docs.rs/rustls/latest/rustls/),
  [Tokio manifest](https://github.com/tokio-rs/tokio/blob/master/tokio/Cargo.toml),
  [rust_socketio published package](https://docs.rs/crate/rust_socketio/latest).
- Desktop/watching: [notify 8.2.2](https://docs.rs/notify/8.2.2/notify/),
  [ashpd 0.14.0](https://docs.rs/ashpd/0.14.0/ashpd/),
  [zbus 6.3.0](https://docs.rs/zbus/6.3.0/zbus/),
  [tray-icon 0.26.1](https://docs.rs/tray-icon/0.26.1/tray_icon/),
  [windows 0.62.2](https://docs.rs/windows/0.62.2/windows/).
- Native support and build: [Rust target support](https://doc.rust-lang.org/rustc/platform-support.html),
  [Windows object namespaces](https://learn.microsoft.com/en-us/windows/win32/termserv/kernel-object-namespaces),
  [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
  [CodeQL language support](https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/),
  [Cargo vendor](https://doc.rust-lang.org/stable/cargo/commands/cargo-vendor.html).
- Licensing/version policy: [GNU license list](https://www.gnu.org/licenses/license-list.html),
  [GNU compatibility explanation](https://www.gnu.org/licenses/license-compatibility.en.html),
  [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html),
  [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
