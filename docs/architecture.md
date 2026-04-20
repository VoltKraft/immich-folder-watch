# Architecture

## Goals

- Watch local folders for new media files.
- Upload files through the Immich HTTP API.
- Keep upload and HTTP behavior isolated from watcher orchestration.
- Run as a per-user desktop app (tray + GUI + sync worker in a single process).

## Solution Layout

- `ImmichFolderWatch.Core`
  - Configuration models, loader, writer, validation
  - File-readiness and batching primitives
  - `FolderWatchWorker` (hosted service) and `WatchSourceFileFilter`
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
2. The app builds the Avalonia `App` and starts with classic-desktop lifetime. When `--autostart` is passed, the main window stays hidden and only the tray icon is shown.
3. `AppHost` constructs an `IHost` that wires:
   - `AppConfig` (loaded from `%LOCALAPPDATA%\Immich Folder Watch\config.yaml`)
   - `IImmichAssetClient` (typed HttpClient)
   - `FolderWatchWorker` (BackgroundService)
   - `ServerConnectionMonitor` (BackgroundService)
   - `SyncStatusProvider` (singleton)
4. The worker creates one `FileSystemWatcher` per source, debounces events, runs readiness checks, dedupes, and flushes batches to the Immich client.
5. Status changes are pushed into `SyncStatusProvider`; the ViewModel and tray tooltip subscribe and re-render on the UI thread.
6. On **Save and Apply**, the ViewModel writes the new YAML and `AppHost.RestartAsync(newConfig)` tears down and rebuilds the internal host.
7. On startup, `LocalizationService.SetLanguage(config.Localization.Language)` resolves `auto`/`en`/`de` to a `CultureInfo` and applies it before the window is built. Runtime language changes raise `LanguageChanged`; `LocalizationProxy` rebroadcasts it as `PropertyChanged(string.Empty)` so every XAML binding (`{Binding X, Source={StaticResource Loc}}`) refreshes. The tray tooltip and permission list subscribe to the same event.

## Design Decisions

- **Per-user, no service.** Multi-user machines get isolated configurations and logs with no privilege escalation at runtime.
- **Single process.** Tray, GUI, and sync worker share memory and push status directly; no RPC, no admin helper, no service control manager calls.
- **Soft server failures.** The server ping is an ongoing background monitor, not a fail-fast startup check — the tray stays alive while the Immich server is temporarily offline.
- **API uploads only:** no direct writes to Immich storage.
- **Path deduplication** is in-memory and runtime-scoped.
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
