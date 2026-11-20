# RW-01 parity and lifecycle reference

Reference product: 3.0.4, source `19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc`.
The fixtures exercise that implementation; they are not replacements for future
production Rust features. The [acceptance record](acceptance.md) distinguishes
reference execution, Rust implementation and native acceptance.

The corpus has three forms:

- [Storage/config oracle](rw01-storage-contract.md): reproducibly generated YAML,
  SQL, JSON, key vectors and source hashes, produced by actual C# APIs in private
  scratch profiles. Linux and Windows outputs remain distinct.
- [Behavior corpus](rw01-behavior-contract.md): language-neutral JSON inputs and
  expected observations consumed by `RustRewriteBehaviorContractTests` using
  production filters/queues/workers/API clients and synthetic HTTP responses.
- [Window traces](../../rust/tests/fixtures/lifecycle/window.json): commands and
  expected visibility/closure/tray-notice states, consumed by
  `RustRewriteLifecycleContractTests` against the real legacy Avalonia view.
  The test host has no production services, profile, network or autostart writes.

Existing C# adversarial/integration tests remain executable specifications for
larger scenarios. Their source is preserved rather than copying every case into
a second test implementation. The [security case map](rw01-security-contract.md)
assigns SEC-01 through SEC-21, including baseline gaps that Rust must improve.

## Full feature mapping

| Parity | Frozen scenarios / reference specifications | Required Rust comparison / acceptance |
| --- | --- | --- |
| PAR-01 | Legacy/default/null/quoted YAML; multi-source overrides; all three modes in `behavior/worker.json`; `AppConfigLoaderTests`, `WatchSourceItemTests` | Exact startup/new-file semantics per mode, multiple simultaneous sources, invalid/legacy normalization, source add/remove and restart |
| PAR-02 | Named vs subfolder albums, root media, duplicate names, membership fallback in HTTP corpus; `FolderWatchWorkerAlbumSecurityTests`, `AlbumOwnershipSecurityTests`, worker persistence suites | Exact-ID membership/provenance and revocation, unassigned root media, trash/local deletion, guarded rename with duplicate/ambiguous events |
| PAR-03 | `normalization`, `filters`, `queue`, `readiness` JSON; `WatchSourceFileFilterTests`, `UploadBatchQueueTests`, download-order tests | Recursion, global/per-source extension/exclusion compatibility, stable ordering, first-attempt priority, retry/backoff, bounded batching; no preemption of active transfers |
| PAR-04 | All schema tables, numeric enums, seven-digit timestamps, repair JSON, tombstone expiry, monotonic history/backfill in oracle; persistence/timestamp suites | No-op startup and unchanged-file fast path without upload/hash/download; crash replay, compare-and-swap repair, Last Sync monotonicity |
| PAR-05 | HTTP/transport JSON, actual multipart device ID vectors, access checker, transfer-security and realtime-transport suites | HTTPS/opt-in HTTP, permissions, endpoint fallbacks, no redirects/origin leaks, bounded complete inventory, full Engine.IO/Socket.IO plus polling and cancellation |
| PAR-06 | Save/Apply JSON; navigation/platform-parity/sync-settings/update view-model tests; `MainWindowBindingTests`, access-check/session-log tests | Overview/Folders/Connection/Settings and folder General/Filters/Advanced; drafts, masked keys, validation-before-save, explicit restart failure, progress/error/history/logs/update link and keyboard flows |
| PAR-07 | Localization, transfer labels and tray-menu tests; real view theme/status/portal-display tests | DE/EN/auto/live switching, retained edits, light/dark/system/high contrast, DPI/multiple monitors, long Unicode paths, IME/paste, screen-reader labels/focus |
| PAR-08 | Per-user Windows/XDG/private-directory tests; autostart protocol tests; window trace corpus; AppHost/Unix instance tests; SEC-17/18/20 | CLI `--autostart`, Linux `--background`, `--migrate-legacy-user`; Startup shortcut/Background portal; native tray/open/restart/Quit and cross-session old/new writer guard; Event Log/journald/file targets |
| PAR-09 | Existing installer static/compiled/installed checks and source identities; `test_windows_installer`, `test_msi_upgrade_contract`, `test_installed_upgrade`, Flatpak source/offline/workflow suites | Four Rust candidates, identity/permissions preserved, .NET-free startup and Event Log resources, actual installation/upgrade/repair/uninstall/rollback, offline reconstruction. Stable signing/catalog publication is RW-08 and excluded |
| PAR-10 | Linux `DBusNotifierTests` fixes protocol payload/priority/IDs/denied/missing/timeout/filter behavior; there is no equivalent complete Windows product baseline | New cross-platform policy below, rate-limiting, privacy, actual native delivery/action and failure behavior |

## Window trace observations

| ID | Input sequence | Observable legacy behavior |
| --- | --- | --- |
| LIFE-01 | Show → Close → Show → Quit | Close hides without closing the window object; reopen works; Quit really closes |
| LIFE-02 | Hidden start → unavailable tray → Close → repeated absence/recovery | Initial missing tray reveals a fallback once; later tray events preserve user-hidden state |
| LIFE-03 | Hidden start → acknowledged tray → host loss → recovery → Quit | Background window remains hidden and notice follows availability |
| LIFE-04 | Show/Close before initial unavailable-tray reply | The delayed reply cannot reopen the user-hidden window |
| LIFE-05 | Hidden start → begin shutdown → unavailable tray → Quit | A startup fallback cannot reopen a shutting-down window |

These are externally reusable C#-validated input/output cases. They do not prove
an engine stayed alive, a real tray registered, a screen reader worked or a GPU
initialized. `AppHostLifecycleTests` separately covers synthetic host start/stop/
restart failure and cancellation; native lifecycle/reachability remains RW-02/06.

## Notification policy selected from the plan

Implement persistent actionable failure and permission-loss notifications, plus
completion notifications only on user request. Repeated offline failures for the
same condition coalesce under a stable event ID; do not notify per transferred
file. Default text must omit API keys, URLs containing credentials and private
filenames. Platform delivery failure becomes a visible capability/error state;
it must not stop safe background work or bypass a denied portal. RW-06 freezes
the exact rate-limit values with tests and verifies native delivery on all targets.

## Baseline gaps and qualification boundaries

The C# reference is an oracle for compatibility, not a universal security pass.
The security map records future-schema WAL mutation, session-scoped Windows
ownership, stalled/unbounded IPC, Windows non-atomic config writes and unbounded
YAML input. Rust must satisfy the stronger selected contract.

Full-disk/kill recovery, interactive graphics/device-loss, accessibility/IME/DPI,
same-SID Windows sessions, UNC, portal/FUSE, native notifications and post-activity
rollback require explicit environments and observations in later packages.
Existing headless/protocol tests or successful cross-builds cannot close them.
