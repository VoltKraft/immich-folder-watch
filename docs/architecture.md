# Architecture

## Goals

- Watch local folders for new media files.
- Upload files through the Immich HTTP API.
- Keep upload and HTTP behavior isolated from watcher orchestration.
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
  - HTTP client implementation for the Immich API
  - Retry and transient error handling
- `ImmichFolderWatch.App`
  - Avalonia desktop UI (MainWindow + ViewModel)
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

## Runtime Flow

1. `Program.Main` acquires a single-instance mutex scoped to the current user SID. If already held, it signals the running instance via a named pipe and exits.
2. The app builds the desktop `App` and starts with classic-desktop lifetime. When `--autostart` is passed on a build with tray support, the main window stays hidden and only the tray icon is shown; the Flatpak package shows the window because its current tray backend is disabled.
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
8. On **Save and Apply**, the ViewModel writes the new YAML and `AppHost.RestartAsync(newConfig)` tears down and rebuilds the internal host. The replacement host reuses the same per-user database.
9. On startup, `LocalizationService.SetLanguage(config.Localization.Language)` resolves `auto`/`en`/`de` to a `CultureInfo` and applies it before the window is built. Runtime language changes raise `LanguageChanged`; `LocalizationProxy` rebroadcasts it as `PropertyChanged(string.Empty)` so every XAML binding (`{Binding X, Source={StaticResource Loc}}`) refreshes. The tray tooltip, where enabled, and permission list subscribe to the same event.

## Design Decisions

- **Per-user, no service.** Multi-user machines get isolated configurations and logs with no privilege escalation at runtime.
- **Single process.** GUI, sync worker, and tray where enabled share memory and push status directly; no RPC, no admin helper, no service control manager calls.
- **One persistent state database per user.** Every watched source shares one `sync-state.db` beside the per-user configuration. Rows are separated by an account-context hash, normalized source path, and relative file path. The API key itself is never stored.
- **Fast restart reconciliation.** The first run with an empty database performs a mode-appropriate bootstrap. Later runs enumerate inexpensive file metadata in the background and use size plus UTC modification time to avoid reprocessing unchanged content.
- **Fail safe state handling.** A corrupt database is quarantined beside the original with a timestamp before a safe bootstrap. If the state cannot be opened or written, transfers stop instead of running without persistent tracking. A source scan that does not complete successfully cannot create deletion decisions.
- **Soft server failures.** The server ping is an ongoing background monitor, not a fail-fast startup check — the desktop app stays alive while the Immich server is temporarily offline.
- **API uploads only:** no direct writes to Immich storage.
- **Path identity follows the platform:** Windows path keys are case-insensitive; Linux path keys preserve case. Identical relative paths in different watched sources remain independent.
- **Single instance per user:** mutex name includes the user SID so different Windows users can run concurrent instances.

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
