# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.4.0] - 2026-04-27

Adds the **Windows Event Log** as the default log target. The dedicated Event
Log named "Immich Folder Watch" is registered by the MSI installer; the GUI
gains a Log Target dropdown and the **Open Logs** button now opens the
relevant location (Event Viewer for the event log, Explorer for files).

### Added
- **`logging.target` config field** with values `eventLog` (default) and
  `file`. Missing or unknown values normalize to `eventLog`, so pre-2.3
  configs load unchanged and switch to Event Log on next save.
- **Settings UI: Log Target dropdown.** When `eventLog` is selected, the
  **Log Directory** field, **Use Default** button and the absolute-path hint
  are hidden (they are only meaningful for the file target).
- **MSI: dedicated custom Event Log registered at install time.** The
  installer creates `HKLM\SYSTEM\CurrentControlSet\Services\EventLog\Immich
  Folder Watch` and a same-named source under it, so the dedicated log
  appears in Event Viewer immediately after install. The component is
  removed on uninstall (entries are kept by Windows convention).
- **Robust fallback** when the Event Log source is missing (e.g. xcopy or
  developer install): the app keeps writing to the configured log directory
  via the existing file appender and surfaces a warning string in the UI.

### Changed
- **"Open Logs" button** now branches on `logging.target`: Event Log →
  `eventvwr.exe /c:"Immich Folder Watch"` (opens straight to the dedicated
  log); File → opens the log directory in Explorer (existing behavior).
- **`AppConfigValidator`** no longer requires `logging.logDirectory` to be
  set or absolute when `logging.target` is `eventLog`.

### Fixed
- **MSI now removes any stale `Immich Folder Watch` source from the standard
  `Application` log on install.** A pre-existing source there (left over from
  a previous run, third-party tool, or test) would otherwise hijack our
  writes: `EventLog.WriteEntry` enforces source/log alignment and throws
  when they mismatch, and `Microsoft.Extensions.Logging.EventLog` silently
  swallows that exception — making the dedicated log appear empty even
  though the provider was active. The MSI's
  `EventLogRegistrationComponent` now performs a `RemoveOnInstall` of
  `HKLM\SYSTEM\CurrentControlSet\Services\EventLog\Application\Immich
  Folder Watch` before writing the canonical registration under the
  dedicated log.
- **`EventLogSourceProbe` now verifies log/source alignment**, not just
  source existence. If the source is registered under a different log,
  the app falls back to file logging with a localized
  `Op_EventLogSourceMisalignedFormat` warning that names the wrong log,
  instead of writes silently disappearing.

### Notes
- Existing on-disk file logs from previous versions are preserved but no
  longer appended to once the target switches to `eventLog`. Switch back
  to **File** in the settings to resume writing to disk.
- The Event Log target is only available on Windows. The app is
  Windows-only by TFM, so this is not a behavior change in practice.

## [2.3.2] - 2026-04-20

A follow-up to 2.3.1 that closes the last missing symmetry gap in `sync` mode:
renames now propagate in both directions between local subfolders and Immich
albums. It also fixes a startup hang where a misbehaving Immich Socket.IO
endpoint could block the worker loop indefinitely.

### Added
- **Bidirectional subfolder ↔ album rename in `sync` mode
  (subfolders-as-albums variant).**
  - Renaming a first-level local subfolder now renames the matching Immich
    album via `PATCH /albums/{id}`. The `_pathToAssetId` map is re-keyed from
    the old to the new prefix so subsequent deletes/moves still target the
    right assets.
  - Renaming an album on Immich now renames the corresponding local subfolder.
    The worker tracks an `album.Id → local-dir-name` map seeded from the
    initial album list and refreshed on every pull; when an album id reappears
    under a different (sanitized) name, the local directory is moved to match.
  - Conflicts (a folder/album with the target name already exists) are logged
    as warnings and leave the existing state untouched — no clobber.
  - New `IImmichAssetClient.RenameAlbumAsync` + `RenameAlbumResult` model
    (404 is idempotently surfaced as `AlbumMissing`, 409 as a conflict
    warning).
  - New `album.update` probe in `ImmichAccessChecker` (gated on
    `requireSyncPermissions`); the GUI's **Verify Immich Access** check now
    covers it alongside the existing `album.delete` / `album.read` /
    `album.create` / `albumAsset.*` / `asset.*` probes.

### Fixed
- **Worker could hang on an unresponsive Socket.IO endpoint.** When the Immich
  instance did not accept the Socket.IO handshake (wrong reverse-proxy path,
  WebSocket disabled, etc.), `SocketIOClient.ConnectAsync` — configured with
  `Reconnection = true` and `ReconnectionAttempts = int.MaxValue` — never
  returned, which blocked `FolderWatchWorker.ExecuteAsync` before the debounce
  / flush / poll loop could start. Symptom: files queued by the initial scan
  and by in-flight `FileSystemWatcher` events never got uploaded, and no
  `Uploading batch` log line ever appeared. The connect is now fired on a
  background `Task.Run`, so the polling loop starts immediately and the
  realtime channel joins in once the socket succeeds (if ever).

## [2.3.1] - 2026-04-20

A follow-up to 2.3.0 focused on making the new `sync` mode feel like a
Nextcloud-grade sync client and on closing the remaining symmetry gaps between
local subfolders and Immich albums.

### Added
- **Realtime downstream sync via Immich Socket.IO.**
  - New `IImmichRealtimeClient` interface (Core) and `ImmichRealtimeClient`
    implementation (Immich project, built on `SocketIOClient` 3.1.2).
  - Subscribes to `on_upload_success`, `on_asset_trash`, `on_asset_delete`,
    `on_asset_update`, `on_asset_restore`, `on_album_create`, `on_album_update`,
    `on_album_delete`, and `on_album_invite`. Any matching event triggers an
    immediate pull on the next 1-second tick of the worker loop.
  - Connects to the Immich root (derived from `ImmichServerApiUrl` by stripping
    the trailing `/api`), authenticates via the `x-api-key` extra header, and
    auto-reconnects on disconnect. Connection failures degrade gracefully to
    the existing polling path.
- **Subfolder ↔ Album symmetry in `sync` mode (subfolders-as-albums variant).**
  - Creating a first-level subfolder now creates the matching Immich album.
  - Deleting a first-level subfolder trashes any assets the app still has
    tracked under that folder, then deletes the Immich album.
  - Renaming a first-level subfolder ensures the new album name exists (rename
    of album membership for existing files is logged as a caveat).
  - New `IImmichAssetClient.EnsureAlbumAsync` / `DeleteAlbumAsync` and result
    models `EnsureAlbumResult` / `DeleteAlbumResult` (404 on delete is
    idempotently treated as success).
  - New `album.delete` probe in `ImmichAccessChecker` (gated on
    `requireSyncPermissions`).
- **Symmetric upload/download status prefix.** Uploads now render as
  `Upload: <filename>` to match the `Download: <filename>` line
  (`Strings.Status_UploadingPrefix`).

### Changed
- **Album pull interval shortened from 60 s to 10 s.** The realtime socket
  makes this interval a safety net rather than the primary trigger, but 10 s
  already gives Nextcloud-level perceived latency when the socket is offline.
- **Default extensions cover Immich's full supported media list.** The
  bootstrapped list for a new source in the Windows GUI — and the example
  config at `packaging/windows/config.windows.example.yaml` — now includes
  all 66 extensions Immich accepts: common images (avif, bmp, gif, heic,
  heif, hif, insp, jp2, jpe, jpeg, jpg, jxl, png, psd, svg, tif, tiff, webp),
  RAW formats (3fr, ari, arw, cap, cin, cr2, cr3, crw, dcr, dng, erf, fff,
  iiq, k25, kdc, mrw, nef, nrw, orf, ori, pef, raf, raw, rw2, rwl, sr2,
  srf, srw, x3f), and videos (3gp, 3gpp, avi, flv, insv, m2t, m2ts, m4v,
  mkv, mov, mp4, mpe, mpeg, mpg, mts, vob, webm, wmv).

### Fixed
- **Permission check state no longer resets on Save.** `MainWindowViewModel.Load`
  now accepts a `resetImmichCheckStatus` flag, and the save path reloads the
  config without clearing the last "Verify Access" result — the badge stays
  where it was before the save.
- **Installer lifecycle.** Uninstall/upgrade paths close the running app
  cleanly (WPF `Application.SessionEnding` handler + WiX `util:CloseApplication`
  with `EndSessionMessage`/`CloseMessage`/`TerminateProcess` fallback), and
  an `MMajorUpgrade` now relaunches the tray app after `InstallFinalize`
  via a `WixShellExec` custom action.

### Infrastructure
- Project, packaging, and release defaults updated to `2.3.1`.
- New `SocketIOClient` 3.1.2 dependency in `ImmichFolderWatch.Immich`.

## [2.3.0] - 2026-04-20

This release introduces per-folder **sync modes**. Each watched source can now
choose how it interacts with Immich: upload only files that appear during
runtime (default, matching the previous behavior), upload the full folder
contents, or keep the folder bidirectionally synchronized with Immich.

### Added
- New `watch.sources[].syncMode` YAML setting with three values:
  - `uploadNew` (default): only new files that appear while the app is running
    are uploaded; pre-existing files are ignored. Preserves the legacy
    behavior end-to-end, so pre-2.3 configs load and run unchanged.
  - `uploadAll`: on start, enqueues every file already in the folder, then
    continues to upload newly added files. No downloads.
  - `sync`: full bidirectional reconciliation with Immich. Two shapes are
    supported based on `albumName`:
    - `albumName` **set** — flat single-album sync. All files in the source
      root mirror the named album. Subfolders are ignored
      (`includeSubdirectories` is forced off).
    - `albumName` **empty** — subfolders-as-albums sync. The root folder
      mirrors all Immich assets without an album, each first-level subfolder
      mirrors the Immich album with the same name, new subfolders become new
      albums, and new Immich albums become subfolders
      (`includeSubdirectories` is forced on).
    Local deletions move the corresponding Immich asset to the trash, and
    moving a file between the parent folder and a subfolder (or between two
    subfolders) updates the asset's album membership on Immich to match.
- `IImmichAssetClient.GetAlbumAssetsAsync` and
  `IImmichAssetClient.DownloadAssetAsync` on top of the Immich routes
  `GET /albums/{id}` and `GET /assets/{id}/original`. Downloads stream to a
  `.downloading` temp file and are moved atomically on completion.
- `IImmichAssetClient.ListAlbumsAsync`, `GetUnassignedAssetsAsync`
  (paginated `POST /search/metadata` with `isNotInAlbum:true`),
  `AddAssetsToAlbumAsync`, `RemoveAssetsFromAlbumAsync`
  (`DELETE /albums/{id}/assets`), and `TrashAssetsAsync`
  (`DELETE /assets` with `force:false`) for the new sync semantics.
- Four new rows in the Immich **Verify Access** permission list:
  `asset.download`, `asset.read`, `asset.delete`, `albumAsset.delete`.
  `ImmichAccessChecker` probes each endpoint with a deliberately invalid id
  and treats `400`, `404`, and `422` as "endpoint reachable, permission ok"
  and `403` as a denial. These probes only **block** config verification when
  at least one source uses `syncMode: sync`; for pure upload configs they
  stay informational (mirrors the existing album-permission gating).
- New **Sync Mode** dropdown on every watched-folder card in the Windows GUI,
  with localized labels and an inline description of the selected mode. The
  `Include subdirectories` checkbox is hidden for `sync` sources.
- New localization strings for the sync-mode UI and the three new permission
  rows in English and German (`UI_SyncMode`, `SyncMode_UploadNew`,
  `SyncMode_UploadAll`, `SyncMode_Sync` and their `_Description` counterparts;
  `Permission_AssetRead`, `Permission_AssetDelete`,
  `Permission_RemoveAssetFromAlbum`).

### Changed
- `FolderWatchWorker` now seeds existing files on start for `uploadAll` and
  `sync` sources (uploads benefit from Immich server-side dedup via the
  `deviceAssetId` hash, so restarts don't re-upload already-known files),
  builds a local-path → Immich-asset-id map on start for `sync` sources, and
  periodically pulls album and unassigned assets for `sync` sources.
- Rename/move events on `sync` sources no longer just log; they now update
  the Immich album membership of the renamed asset, and local deletions
  trash the corresponding Immich asset instead of being ignored.
- Windows GUI, YAML loader/writer, and config model now round-trip the new
  `syncMode` field; unknown or missing values normalize to `uploadNew`.
- Project, packaging, and release defaults updated to `2.3.0`.

## [2.2.0] - 2026-04-20

This release makes the Windows GUI follow the active Windows 11 design system
end-to-end: light/dark chrome, the user's accent color, and live updates when
either setting changes — no restart required.

### Added
- Live detection of the Windows accent color from
  `HKCU\Software\Microsoft\Windows\DWM\AccentColor` in `ThemeWatcher`, with
  programmatic Fluent shades (`AppAccentLight1..3`, `AppAccentDark1..3`)
  published as dynamic brushes on `Application.Resources`.
- `WM_DWMCOLORIZATIONCOLORCHANGED` and `WM_THEMECHANGED` are now hooked on the
  main window alongside `WM_SETTINGCHANGE`, so changing the accent color (or
  switching light/dark) in Windows Settings updates the UI immediately.
- New theme-aware header-icon brushes (`AppHeaderIconBackground`,
  `AppHeaderIconBorder`) so the logo tile stays visible in both light and dark
  mode instead of relying on a hardcoded white overlay.

### Changed
- Primary button, focused text-box border, and info status pill now pull from
  the Windows accent color. In dark mode they use a lighter accent shade with
  black foreground (Windows 11 convention); in light mode the base accent with
  white foreground.
- Light and dark palettes retuned to Windows 11 Fluent chrome values
  (`#F3F3F3` / `#202020` base, matching card, border, surface, footer, and
  status tones) so the window chrome aligns with native Windows 11 apps.
- The header bar is now theme-aware instead of always rendering in a dark navy
  shade, so it follows the active system theme together with the rest of the
  window.
- Project, packaging, and release defaults updated to `2.2.0`.

## [2.1.0] - 2026-04-20

This release adds full UI localization. The app ships with English as the neutral
fallback and a complete German translation; the active language is detected from
the operating system by default, can be pinned in the config file, and can be
changed at runtime through a new dropdown in the GUI without restarting.

### Added
- .resx-backed localization (`Strings.resx` neutral/English, `Strings.de.resx`
  German) covering every tray menu entry, window label, watermark, status badge,
  tooltip, permission display name, and operation message.
- `LocalizationService` (singleton) that resolves `auto`/`en`/`de` to a
  `CultureInfo`, applies it to the thread and default thread cultures as well as
  `Strings.Culture`, and raises `LanguageChanged` on switch.
- `LocalizationProxy` (`INotifyPropertyChanged`) registered in `App.xaml` as
  `{StaticResource Loc}`; broadcasts `PropertyChanged(string.Empty)` on language
  change so every XAML binding refreshes immediately without reopening the
  window.
- New **Appearance → Language** dropdown in the GUI with three entries
  (`Auto (system default)`, `English`, `Deutsch`); the selection is persisted
  on the next Save.
- New YAML setting `localization.language` (`auto` | `en` | `de`). Missing,
  blank, or unknown values normalize to `auto`.

### Changed
- Tooltip composition moved from `SyncStatusProvider` (Core) to
  `TrayIconHost` (App) so it can read localized strings; Core no longer depends
  on App resources and `SyncStatusProvider.TooltipText` was removed.
- `MainWindowViewModel` now takes a `LocalizationService`, subscribes to
  `LanguageChanged`, and rebuilds all `Strings.*`-backed fields — including the
  permission status list — on language change.
- All previously hardcoded German or English UI literals in `MainWindow.xaml`,
  `MainWindow.xaml.cs`, `TrayIconHost.cs`, and `MainWindowViewModel.cs` now pull
  from `Strings.*` (English stays as the neutral fallback).

## [2.0.0] - 2026-04-20

This release replaces the Windows service model with a tray-based desktop application
and rewrites the GUI from Avalonia to WPF. The Windows executable is renamed and the
installer no longer registers a background service; existing installations are
migrated automatically.

### Added
- Native Windows tray icon with a right-click menu to open the GUI, restart sync, or
  quit, implemented on a message-only window via `Shell_NotifyIconW` and
  `TrackPopupMenuEx` so no extra top-level windows appear in Task Manager.
- System-synced dark mode for the WPF window chrome via
  `DWMWA_USE_IMMERSIVE_DARK_MODE`, and dark-aware tray context menus via
  `SetPreferredAppMode(AllowDark)`.
- `PasswordBoxHelper` attached property for two-way binding of the Immich API key
  from a `PasswordBox`, and `WatermarkBehavior` attached property for placeholder
  text on `TextBox` and `PasswordBox`.
- Autostart integration that places a shortcut in the per-user Startup folder on
  first run and launches the app hidden to the tray with `--autostart`.
- Single-instance coordinator that forwards a second launch to the running instance
  and shows its window instead of starting a duplicate.
- Migration of legacy per-machine `ProgramData\Immich Folder Watch\config.yaml` into
  the new per-user location on upgrade (`--migrate-legacy-user`).

### Changed
- **Breaking:** the Windows binary is now `ImmichFolderWatch.exe` (previously
  `ImmichFolderWatch.App.exe`). Shortcuts, scripts, and installer references have
  been updated; upgrades via MSI handle this automatically, manual launchers must be
  repointed.
- **Breaking:** the app now runs as a user-space WPF application with a tray icon
  instead of a Windows service. The previous `ImmichFolderWatch` service is stopped,
  removed, and its `ProgramData` directory cleaned up during upgrade.
- Configuration and logs moved from `C:\ProgramData\Immich Folder Watch\` to
  `%LOCALAPPDATA%\Immich Folder Watch\`.
- GUI rewritten from Avalonia 11 to WPF on `net10.0-windows`; Avalonia,
  `H.NotifyIcon.Avalonia`, Skia, and HarfBuzz dependencies removed, reducing
  install size and resident memory.
- Replaced `IHttpClientFactory` with a single `HttpClient` backed by a
  `SocketsHttpHandler` with `PooledConnectionLifetime = 10 min`, eliminating the
  2-minute handler rotation that previously caused WMI counter churn visible as
  stray Task Manager children.
- Theme changes are now detected by hooking `WM_SETTINGCHANGE` on the main window
  instead of subscribing to `Microsoft.Win32.SystemEvents`, which had been creating
  a hidden broadcast window that appeared as a nameless child in Task Manager.
- Log writer now opens files with `FileShare.ReadWrite` to prevent save-and-apply
  from racing against the active log handle during restart.
- Installer (WiX) updated to install only the GUI binary, create a desktop shortcut,
  clean up the legacy service and its data directory, and wire the user-config
  migration through `WixQuietExecCmdLine`.
- Branding asset generation now runs before `MarkupCompilePass1`, and the generated
  `app-icon.ico` / `header-logo.png` are declared as top-level `<Resource>` items so
  they are embedded correctly in the WPF resource stream.
- Project, packaging, and release defaults updated to `2.0.0`.

### Removed
- Windows service hosting (`ImmichFolderWatch` service) and the related
  service-control UI in the previous GUI.
- `Microsoft.Extensions.Http` package reference.
- Avalonia UI stack (`Avalonia`, `Avalonia.Desktop`, `Avalonia.Themes.Fluent`,
  `Avalonia.Svg.Skia`, `Avalonia.Diagnostics`) and `H.NotifyIcon.Avalonia`.
- `UseWindowsForms` dependency and the WinForms parking window it implied.

### Fixed
- Save-and-apply no longer fails with a file-in-use error on the active log file
  during the subsequent restart.
- Windows Task Manager no longer shows a nameless child process underneath the
  application entry.
- MSI upgrade now reliably chains the `QuietExec` custom actions for stopping and
  removing the legacy service and migrating user config.

## [1.6.3] - 2026-03-21

### Changed
- MSI- and WinGet-driven Windows upgrades now start the `ImmichFolderWatch` service again automatically when it was running before the upgrade and the installed ProgramData config still validates successfully.
- Project, packaging, and release defaults updated to `1.6.3`.

## [1.6.2] - 2026-03-21

### Changed
- Added a central branding asset pipeline with assets/branding/logo.svg as the single maintained source for GUI, installer, README, and future Flatpak icon derivatives.
- Windows GUI builds now generate and embed the application icon plus a header logo automatically, and the MSI package now reuses the same generated icon for ARP and the desktop shortcut.
- README and Flatpak placeholder documentation now describe the shared branding asset flow.
- The branding asset generator now disposes the SKPicture loaded from SKSvg.Load correctly.
- Project, packaging, and release defaults updated to 1.6.2.

## [1.6.1] - 2026-03-21

### Changed
- `StatusTone` and the reusable `StatusPill` control are now documented and use simpler built-in class toggling for tone updates.
- Windows GUI theme resources now use the consistent `AppButtonPrimary*` naming pattern for primary buttons.
- Version fallback handling in the GUI and daemon tests now avoids duplicated hardcoded literals, and Immich permission tone tests now assert that the permission list is populated before validating item tones.
- Project, packaging, and release defaults updated to `1.6.1`.

## [1.6.0] - 2026-03-21

### Changed
- The Windows GUI now follows the active system light/dark theme and uses theme-aware colors for cards, header, footer, buttons, and status badges.
- Status badges in the Windows GUI now use reusable tone-based styling so `Verify Immich Access`, service controls, and permission states stay readable in both light and dark mode.
- Project, packaging, and release defaults updated to `1.6.0`.

## [1.5.0] - 2026-03-13

### Added
- Per-source `watch.sources[].extensions` include lists in the daemon, GUI, and YAML config.
- Per-source `watch.sources[].excludeDirectories` and `watch.sources[].excludeFileNames` glob filters for skipping subfolders and file names.

### Changed
- Existing `1.4.x` configs that still use top-level `watch.extensions` now migrate automatically to the per-source schema when loaded and are rewritten in the new format on save.
- The Windows GUI now configures extensions and exclude lists directly on each watched source card instead of using one global extensions field.
- The Windows GUI now keeps per-source subdirectory, extension, and exclude settings inside a collapsed **Advanced Watch Options** section by default.
- New GUI watch sources and the Windows example config now prefill the full official Immich image-extension list, and `Excluded Directories` is shown only when subdirectory watching is enabled.
- Project, packaging, and release defaults updated to `1.5.0`.

## [1.4.0] - 2026-03-08

### Changed
- Uploads can now place new files into the configured `watch.sources[].albumName`, create missing albums automatically, and fail clearly when duplicate exact-name albums already exist.
- `watch.sources[].albumName` is now optional. Leaving it empty uploads files without assigning them to an album.
- The Windows GUI now suggests the watched folder name once for a new source's `Immich Album Name` field and keeps a deliberately cleared value empty afterwards.
- Immich album permissions now become blocking only when the current configuration actually uses album placement.
- Project, packaging, and release defaults updated to `1.4.0`.

## [1.3.1] - 2026-03-08

### Fixed
- The Immich API key reveal button in the Windows GUI now correctly toggles between masked and visible display for real API keys.

### Changed
- Project, packaging, and release defaults updated to `1.3.1`.

## [1.3.0] - 2026-03-08

### Changed
- Windows installations now store the active config under `C:\ProgramData\Immich Folder Watch\config.yaml` and logs under `C:\ProgramData\Immich Folder Watch\logs\`, while binaries remain under `%ProgramFiles%\Immich Folder Watch\bin\`.
- Windows upgrades and script-based installs now migrate the old default Program Files config and log layout into the new ProgramData location automatically.
- Successful GUI saves now migrate existing log files when `logging.logDirectory` changes, keeping already existing target files and skipping only conflicting source files.
- The GUI header status/details area now uses the available width instead of clipping or wrapping early at a fixed narrow width.
- The GUI now masks real Immich API keys by default, adds a reveal toggle, and keeps the example placeholder visible in plain text so it is obvious when it still needs to be replaced.
- Project, packaging, and release defaults updated to `1.3.0`.

## [1.2.3] - 2026-03-08

### Changed
- The Windows GUI no longer stores a separate `activation-state.json` file for persistent verified state.
- The service status panel no longer shows `Verified: Yes/No`.
- GUI saves now treat local validation plus the Immich check as the authoritative verification step each time the config is applied.
- README and Windows installation docs now describe the save-time verification flow without a persistent verified-state file.
- Project, packaging, and release defaults updated to `1.2.3`.

## [1.2.2] - 2026-03-08

### Added
- The Windows GUI now shows the current app version in the header.

### Changed
- The main GUI action now switches between **Save and Start** and **Save and Restart** based on the current service state.
- Saving a verified config now starts an already verified but currently stopped service again.
- GUI-triggered service start and restart actions now normalize the service startup type to `Automatic (Delayed Start)`, unless the service is already configured as `Automatic` without delay.
- Project, packaging, and release defaults updated to `1.2.2`.

## [1.2.1] - 2026-03-08

### Fixed
- Windows installs and upgrades now default the service startup mode to `Manual` instead of leaving it `Disabled`.
- MSI upgrades now normalize previously disabled installs to `Manual` so the GUI and admin helper can start the service again without a manual Services.msc change.

### Changed
- Script-based Windows service installation now defaults to `Manual` startup as well.
- Project, packaging, and release defaults updated to `1.2.1`.

## [1.2.0] - 2026-03-08

### Added
- GUI check for Immich URL, API key, and the permissions required for upload plus the planned album workflow.
- Automatic one-time Immich access check when the Windows GUI opens.
- Visual service-state badge and context-aware **Start Service**, **Stop Service**, and **Restart Service** actions in the GUI.

### Changed
- The GUI now surfaces URL, API key, and permission results separately instead of only reporting a single verification outcome.
- The **Watch Sources** editor now labels the album field as **Immich Album Name**.
- Project, packaging, and release defaults updated to `1.2.0`.
- README now documents the expanded GUI verification and service-control workflow.

## [1.1.0] - 2026-03-08

### Added
- Windows desktop GUI for guided configuration, log-folder adjustment, quick log access, and service activation after successful verification.
- Automatic service-status refresh in the GUI so state changes are reflected without reloading the form.

### Changed
- Windows installations now keep the service disabled until the first successful **Save And Verify** from the GUI.
- `logging.logDirectory` is now expected to be configured as an absolute path, and the GUI upgrades existing relative values to an absolute path when opened.
- Project, packaging, and release defaults updated to `1.1.0`.
- README and Windows-facing documentation now describe the GUI-first setup flow.

## [1.0.1] - 2026-03-07

### Added
- In-repo WinGet metadata and bootstrap documentation for `VoltKraft.ImmichFolderWatch`.
- Dedicated GitHub Actions workflow for post-bootstrap WinGet package updates.

### Changed
- Windows installations now default to `Automatic (Delayed Start)` service registration instead of manual startup.
- The top-level README now focuses on what the program is, what it does, and how to use it.
- Project and packaging version defaults updated to `1.0.1`.
- MSI publisher metadata now aligns with the planned WinGet publisher identity `VoltKraft`.

## [1.0.0] - 2026-03-07

### Added
- First supported Windows release of `immich-folder-watch`.
- Windows service installation via PowerShell bundle and MSI packaging.
- Structured Windows install layout with `bin\`, `config\config.yaml`, and `logs\`.
- Automatic migration of legacy Windows root-level `config.yaml` into `config\config.yaml`.
- GitHub Actions release workflow that publishes and updates the current versioned release from `main` using this changelog entry.

### Changed
- Project version updated to `1.0.0`.
- README and Windows documentation updated to reflect the current Windows-first release status.
- Project documentation now explicitly states that this is not a sync client and only uploads files that appear while the daemon is running.
- Linux installation documentation now reflects that a supported Linux release is not available yet.

### Previous Work Included In 1.0.0
- Initial repository scaffold for `immich-folder-watch`.
- Cross-platform daemon with folder watching, batching, and Immich API uploads.
- YAML configuration loading and validation via `YamlDotNet`.
- Unit tests for core logic.
- CI, release, and Flatpak placeholder workflows.
