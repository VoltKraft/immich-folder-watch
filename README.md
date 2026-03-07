# immich-folder-watch

[![CI](https://img.shields.io/badge/CI-pending-lightgrey?logo=githubactions)](./.github/workflows/ci.yaml)
[![Version](https://img.shields.io/badge/Version-1.0.0-blue)](./CHANGELOG.md)
[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](./LICENSE)

Windows service that watches local folders and uploads newly appearing files to Immich through the Immich HTTP API.

> [!IMPORTANT]
> This project uploads files through the Immich API. It does **not** write files directly into Immich storage.

> [!IMPORTANT]
> This is **not** a sync client like Nextcloud. It does not mirror folders, propagate deletes, or backfill files that were already present before the daemon started. It only uploads files that generate file-system events while the daemon is running.

## Project Status

Version `1.0.0` is the first supported Windows release.

### Supported in 1.0.0
- [x] Windows-first .NET 10 daemon
- [x] YAML configuration via `YamlDotNet`
- [x] Multiple watched source folders
- [x] File debouncing and file-ready checks for partial writes
- [x] Upload of newly appearing files while the daemon is running
- [x] Batch uploads with deduplication within one runtime session
- [x] Immich API upload client isolated in its own project
- [x] Retry with exponential backoff for transient upload failures
- [x] Unit tests for config parsing, file-ready behavior, and batching logic
- [x] Cross-platform CI build/test coverage for the codebase
- [x] Scriptable Windows service packaging with install/uninstall PowerShell automation
- [x] MSI-based Windows installer build with service registration

### Not part of 1.0.0
- [ ] Folder sync comparable to Nextcloud
- [ ] Startup backfill of files that already exist before the daemon starts
- [ ] Delete or rename synchronization into Immich
- [ ] Supported Linux installation or Linux service packaging
- [ ] Flatpak packaging

### Planned next
- [ ] Bootstrapper `.exe` for one-click distribution
- [ ] Winget distribution
- [ ] Album management enhancements based on Immich API evolution
- [ ] Rich observability (metrics, optional OpenTelemetry)

## Why This Project

| Problem | This project does |
| --- | --- |
| Screenshot folders fill up quickly | Watches one or more local folders continuously |
| Manual uploads are repetitive | Uploads new files automatically in batches |
| A full sync client would be overkill | Focuses on upload-on-arrival automation |
| Direct file-copy bypasses Immich indexing | Uses Immich HTTP API so assets appear immediately |
| Temporary file writes trigger broken uploads | Waits until files are readable before upload |

## Quickstart (Windows)

1. Install .NET SDK 10.0 or newer, or use the Windows installer artifacts.
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
- [Linux Status](./docs/installation-linux.md)
- [Troubleshooting](./docs/troubleshooting.md)
- [Development](./docs/development.md)

## License

This repository is licensed under **AGPL-3.0-only**. See [LICENSE](./LICENSE).
