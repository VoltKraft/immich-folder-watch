# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
