# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
