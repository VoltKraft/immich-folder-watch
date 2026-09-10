# Architecture

## Goals

- Support per-folder upload modes and bidirectional synchronization with Immich.
- Transfer media, manage album membership, and propagate supported deletion and
  rename operations through the Immich API.
- Keep HTTP and realtime API integration isolated from synchronization orchestration.
- Run as a per-user desktop app (GUI + sync worker in a single process; tray
  support is available on Windows and disabled in the Flatpak package).

## Solution Layout

- `ImmichFolderWatch.Core`
  - Configuration models, loader, writer, validation
  - File-readiness and batching primitives
  - `FolderWatchWorker` (hosted service) and `WatchSourceFileFilter`
  - Versioned SQLite sync-state store shared by every watched source
  - `SyncStatusProvider` (INotifyPropertyChanged push surface)
  - `ServerConnectionMonitor` (periodic Immich ping)
  - File-based log provider
  - `InstallationPaths` (per-user `%LOCALAPPDATA%` locations + legacy ProgramData lookup)
- `ImmichFolderWatch.Immich`
  - HTTP client for media uploads/downloads, albums, and asset trash operations
  - Socket.IO notifications that trigger reconciliation of remote changes
  - Retry and transient error handling
- `ImmichFolderWatch.App`
  - Windows WPF desktop UI (MainWindow, with shared ViewModel)
  - Tray icon, tooltip, and context menu (Open, Restart, Quit)
  - `AppHost` — owns the internal `IHost` that runs the sync worker
  - `AutostartManager` — Startup-folder `.lnk` management via WScript.Shell COM
  - `SingleInstanceCoordinator` — SID-scoped mutex + named-pipe "show GUI" IPC
  - `LocalizationService` + `LocalizationProxy` — .resx-backed UI localization
    (English neutral, German translated) with OS auto-detect and live switching
  - Embedded resources: `Resources/Strings.resx`, `Resources/Strings.de.resx`
  - CLI flags: `--autostart`, `--migrate-legacy-user`
- `ImmichFolderWatch.Tests`
  - Unit tests for config parsing, readiness checks, batching/dedup
  - Unit tests for config verification, file filtering, installation paths, ViewModel state

The Linux-specific acceptance matrix and intentional platform differences are
tracked in [Linux feature parity](qa/linux-parity.md).

## Runtime Flow

1. `Program.Main` acquires a single-instance mutex scoped to the current user SID. If already held, it signals the running instance via a named pipe and exits.
2. The app builds the desktop `App` and starts with classic-desktop lifetime. When `--autostart` is passed, the main window starts hidden. The tray registers with the desktop watcher; if registration fails or the watcher disappears, the application shows the window so it remains reachable. Flatpak uses the same behavior.
3. `AppHost` constructs an `IHost` that wires:
   - `AppConfig` (loaded from `%LOCALAPPDATA%\Immich Folder Watch\config.yaml`)
   - the shared sync-state store (`sync-state.db` beside `config.yaml`)
   - `IImmichAssetClient` (typed HttpClient)
   - `FolderWatchWorker` (BackgroundService)
   - `ServerConnectionMonitor` (BackgroundService)
   - `SyncStatusProvider` (singleton)
4. The worker opens the shared, versioned SQLite database, loads the state for the configured Immich account and sources, then starts one `FileSystemWatcher` per source.
5. The worker reconciles local metadata in the background. The source path and relative file path identify a file within an account context; size and UTC modification time form the fast fingerprint. Matching files are skipped without hashing, API calls, uploads, or downloads. New or changed files continue through readiness checks, deduplication, and transfer batching.
6. A successful upload is committed only after the transfer, any requested album placement, and a final check that the local file did not change during transfer. A download is committed only after its temporary file has been atomically renamed into place. Tombstones preserve completed deletion and move decisions across restarts.
7. Status changes are pushed into `SyncStatusProvider`; the ViewModel and, where enabled, the tray tooltip subscribe and re-render on the UI thread.
8. On **Save and Apply**, both windows call the shared `ConfigApplyService`. It normalizes and validates the draft, checks required Immich permissions, and writes YAML through `AppConfigWriter` only after validation succeeds. It then awaits `AppHost.RestartAsync(newConfig)`. The replacement host reuses the same per-user database. Local validation and failed access checks do not write or restart; a restart failure is reported after saving.
9. On startup, `LocalizationService.SetLanguage(config.Localization.Language)` resolves `auto`/`en`/`de` to a `CultureInfo` and applies it before the window is built. Runtime language changes raise `LanguageChanged`; `LocalizationProxy` rebroadcasts it as `PropertyChanged(string.Empty)` so every XAML binding (`{Binding X, Source={StaticResource Loc}}`) refreshes. The tray tooltip, where enabled, and permission list subscribe to the same event.

The Linux tray exports StatusNotifierItem and DBusMenu through a dedicated D-Bus
connection under `io.github.voltkraft.immich-folder-watch.Tray`. This namespace is
already owned by the Flatpak app; only watcher communication needs an explicit
`org.kde.StatusNotifierWatcher` talk rule. Availability follows acknowledged
registration, watcher changes trigger re-registration, and disposing the
connection withdraws the item and menu together.

Linux notifications use the version-1 Notification portal contract over the
shared session connection. Each event gets a unique ID, so later events do not
replace earlier ones. Submission waits at most three seconds; failures are
logged, caller cancellation propagates, and desktop presentation is not
observable through this API. No direct notification-daemon permission is needed.

## Design Decisions

- **Recoverable download timestamps.** Original creation time is independent of
  transfer ordering and server upload time. New downloads apply platform-specific
  timestamps before storing their filesystem fingerprint. Existing download
  mappings use an additive `sync_timestamp_repairs` SQLite journal containing the
  old mapping, desired UTC timestamps and content SHA-256. Completion atomically
  updates the mapping and removes the journal; startup recovery precedes upload
  reconciliation. Metadata-only corrections never advance transfer history.
  Readback accounts for filesystem precision. An ambiguous edit or journal failure
  pauses the worker without flushing uploads. See [downloaded file dates](configuration.md#downloaded-file-dates).

- **Durable last-transfer history.** The state store keeps an account-scoped high-water timestamp independently of file entries. The worker reads it before registration/reconciliation and explicitly writes after a successful upload/download, before reporting completion to the UI. Generic entry upserts never update it. An additive auxiliary table preserves schema-version-1 compatibility and is seeded once from available synchronized records for old installations; this backfill is approximate because historic entries did not distinguish transfer and reconciliation timestamps. Status restoration and completion use a worker-session token so a late completion during a timed-out shutdown cannot overwrite a newly selected account's history. Timestamp updates are monotonic in both SQLite and the UI.

- **Shared draft, transient navigation.** Both desktop heads expose Overview, Folders, Connection, and Settings through the same `MainWindowViewModel` selection state. The folder editor binds to an existing `WatchSourceItem` in `Sources`, not a copy, so switching views cannot discard uncommitted edits. Collection changes reconcile the selection; loading an applied configuration restores it by path or index. Navigation state is not serialized. `DisplayName` is derived from `DisplayPath`, preserving Linux portal-path identity. Page-local scroll regions leave status and apply actions reachable. See [Desktop interface](user-interface.md) for the control map and upgrade behavior.

- **Per-user, no service.** Multi-user machines get isolated configurations and logs with no privilege escalation at runtime.
- **Single process.** GUI, sync worker, and tray where enabled share memory and push status directly; no RPC, no admin helper, no service control manager calls.
- **One persistent state database per user.** Every watched source shares one `sync-state.db` beside the per-user configuration. Rows are separated by an account-context hash, normalized source path, and relative file path. The API key itself is never stored.
- **Fast restart reconciliation.** The first run with an empty database performs a mode-appropriate bootstrap. Later runs enumerate inexpensive file metadata in the background and use size plus UTC modification time to avoid reprocessing unchanged content.
- **Fail safe state handling.** A corrupt database is quarantined beside the original with a timestamp before a safe bootstrap. If the state cannot be opened or written, transfers stop instead of running without persistent tracking. A source scan that does not complete successfully cannot create deletion decisions.
- **Soft server failures.** The server ping is an ongoing background monitor, not a fail-fast startup check — the desktop app stays alive while the Immich server is temporarily offline.
- **Global transfer priority.** First upload attempts take priority over retries; the configured timestamp order applies within each group before selecting a batch. Each worker iteration processes at most one batch so new filesystem events and remote pulls remain responsive. Pending downloads are sorted per source/album. Source traversal and transfer readiness remain independent of priority; active transfers are never interrupted to reorder files.
- **Persistent operation progress in the UI.** Sync status retains processed/total counts after an upload cycle or scan of all sync sources finishes, but hides them while inactive. Upload counts span successive batches while the ready queue remains nonempty and are kept separately from intervening downloads; retries after the queue drains start a new cycle. Active transfers and sync errors display the counts. Download totals grow as pending files are discovered per album; empty scans retain previous counts. Only completed attempts count as processed, including failures and skips. Server connectivity errors and sync errors have separate status fields so a successful ping does not hide a failed transfer. Pull errors survive subsequent albums in the same scan and clear after a later complete successful scan.
- **API-only Immich integration:** uploads, downloads, album changes, and asset
  trash operations use the Immich API; no direct access to Immich storage.
- **Path identity follows the platform:** Windows path keys are case-insensitive; Linux path keys preserve case. Identical relative paths in different watched sources remain independent.
- **Single instance per user:** mutex name includes the user SID so different Windows users can run concurrent instances.

## Release distribution

GitHub publication remains atomic across both Windows MSIs and both Linux
Flatpaks from one commit. WinGet and Flathub updates run independently after that
publication. Flathub receives a source manifest and one combined offline NuGet
feed, checked by native build jobs for both x86_64 and aarch64, because updating
the Git tag alone would leave its dependency inputs stale. The accepted Flathub
repository builds and publishes its own package through an update PR; upstream
never uploads a GitHub Flatpak bundle to Flathub. Submission and automerge are
separately enabled after external approval. See
[Flathub preparation](../packaging/flatpak/flathub/README.md) for requirements,
activation and failure handling.

The Flatpak build uses current Freedesktop 26.08 and exact architecture-specific
Microsoft .NET SDK archive sources. The SDK stays inside the module build tree;
only the self-contained application is exported. NuGet preparation must use
the same SDK version as offline publication. This removes the dependency on a
matching .NET Flatpak SDK extension while making SDK security updates an
explicit packaging maintenance responsibility.

## Immich API Assumptions

The Immich API can evolve. The following assumptions are centralized in
`src/ImmichFolderWatch.Immich/ImmichApiRoutes.cs` and
`src/ImmichFolderWatch.Immich/ImmichAssetClient.cs`.

- Base API URL ends with `/api`.
- Ping endpoint candidates: `server/ping`, `server-info/ping`.
- Upload endpoint candidate: `assets` (multipart form upload).
- Multipart includes `assetData` and metadata fields used by current client.

If Immich changes endpoints or required multipart fields, update only the
Immich project while keeping the App and Core layers stable.
