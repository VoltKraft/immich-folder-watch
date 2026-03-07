# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
