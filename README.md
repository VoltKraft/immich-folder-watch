# immich-folder-watch

[![CI](https://img.shields.io/badge/CI-pending-lightgrey?logo=githubactions)](./.github/workflows/ci.yaml)
[![Release](https://img.shields.io/badge/Release-pending-lightgrey?logo=github)](./.github/workflows/release.yaml)
[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](./LICENSE)

Upload new screenshots and media from local folders to Immich automatically using the Immich HTTP API.

> [!IMPORTANT]
> This project uploads files through the Immich API. It does **not** write files directly into Immich storage.

## Project Status

### ✅ Implemented now
- [x] Cross-platform .NET daemon with primary Windows-first workflow
- [x] YAML configuration via `YamlDotNet`
- [x] Multiple watched source folders
- [x] File debouncing and file-ready checks for partial writes
- [x] Batch uploads with deduplication within a runtime session
- [x] Immich API upload client isolated in its own project
- [x] Retry with exponential backoff for transient upload failures
- [x] Unit tests for config parsing, file-ready behavior, and batching logic
- [x] CI workflow for Windows and Linux build/test

### 🚧 In progress
- [ ] Hardened Windows Service packaging and install UX
- [ ] Linux `systemd` service packaging scripts
- [ ] Flatpak packaging pipeline and runtime integration

### 🗺️ Planned
- [ ] Winget distribution
- [ ] Flathub distribution
- [ ] Album management enhancements based on Immich API evolution
- [ ] Rich observability (metrics, optional OpenTelemetry)

## Why This Project

| Problem | This project does |
| --- | --- |
| Screenshot folders fill up quickly | Watches one or more local folders continuously |
| Manual uploads are repetitive | Uploads new files automatically in batches |
| Direct file-copy bypasses Immich indexing | Uses Immich HTTP API so assets appear immediately |
| Temporary file writes trigger broken uploads | Waits until files are readable before upload |

## Quickstart (Windows Console Mode)

1. Install .NET SDK 8.0 or newer.
2. Copy the example config:
   - `cp examples/config.example.yaml config.yaml`
3. Edit `config.yaml` with your Immich API URL and API key.
4. Build and run:

```powershell
dotnet restore
dotnet build .\ImmichFolderWatch.sln -c Release
dotnet run --project .\src\ImmichFolderWatch.Daemon -- --config .\config.yaml
```

## Documentation

- [Architecture](./docs/architecture.md)
- [Configuration](./docs/configuration.md)
- [Windows Installation](./docs/installation-windows.md)
- [Linux Installation](./docs/installation-linux.md)
- [Flatpak Notes](./docs/flatpak.md)
- [Troubleshooting](./docs/troubleshooting.md)
- [Development](./docs/development.md)

## License

This repository is licensed under **AGPL-3.0-only**. See [LICENSE](./LICENSE).
