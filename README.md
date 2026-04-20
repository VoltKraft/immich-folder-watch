<p align="center">
  <img src="./assets/branding/logo.svg" alt="Immich Folder Watch logo" width="128" />
</p>

# Immich Folder Watch

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11%2FServer-0078D6?logo=windows)](./docs/installation-windows.md)
[![Version](https://img.shields.io/badge/Version-2.2.0-blue)](./CHANGELOG.md)
[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](./LICENSE)

`Immich Folder Watch` is a Windows desktop app that watches local folders and uploads newly created media to Immich automatically.

It runs as a per-user tray app — no Windows service, no elevation on every change. If screenshots, camera imports, scanner output, or synced files land on a Windows machine before they land in Immich, this fills that gap without writing directly into Immich storage.

---

## Use Cases

- Automatically upload screenshots into an Immich album
- Watch a DSLR or SD-card import folder and send new photos to Immich
- Ingest scanner output into a family archive
- Pick up files dropped by another tool into a staging folder
- Run a small always-on system that feeds Immich in the background
- Separate sources by album, for example `Screenshots`, `Camera Imports`, or `Receipts`


---

## Solution

`immich-folder-watch` watches one or more folders, waits until files are fully written, and uploads them through the normal Immich HTTP API.

That gives you a clean, low-maintenance ingestion path:

- Windows-first setup with a desktop GUI and tray icon
- Per-user operation — each Windows user runs their own configuration
- Autostart on login (toggleable in the GUI)
- Optional per-folder album placement in Immich
- API-based uploads instead of storage hacks

It is intentionally not a two-way sync client. It does not mirror deletions, does not backfill files that already existed before the app started, and does not write directly into Immich's storage folders.

---

## Features

- Watches one or more local folders for new media files
- Waits until files are stable before upload
- Uploads through the Immich API in configurable batches
- Supports optional per-source `albumName`
- Creates missing albums automatically when album placement is configured
- Retries transient upload failures automatically
- Runs as a per-user tray app with live sync status
- Autostarts on login by default; togglable in the GUI
- Verifies Immich URL, API key, and required permissions from the GUI
- Localized UI (English, German) with OS auto-detect and live in-app language switching

---

## Installation

### Recommended: Windows MSI

1. Download the latest MSI from [GitHub Releases](https://github.com/VoltKraft/immich-folder-watch/releases).
2. Install it with administrative rights (per-machine binary install).
3. Open the `Immich Folder Watch` desktop shortcut.
4. Enter your Immich URL and API key and review the verification result.
5. Select one or more folders and expand **Advanced Watch Options** only when you want to adjust subdirectories, extensions, or exclude filters.
6. **Save and Apply** — watching starts in-process.

Each Windows user has their own configuration. The app autostarts at login by default.

Installed layout:

- Binaries: `%ProgramFiles%\Immich Folder Watch\bin\` (shared, per-machine)
- Config: `%LOCALAPPDATA%\Immich Folder Watch\config.yaml` (per user)
- Logs: `%LOCALAPPDATA%\Immich Folder Watch\logs\` (per user)
- Autostart: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Immich Folder Watch.lnk`

Upgrading from an older service-based install: the legacy service is stopped and removed, and the existing `C:\ProgramData\Immich Folder Watch\config.yaml` is migrated into the installing user's `%LOCALAPPDATA%`.

Detailed guides:

- [Windows Installation](./docs/installation-windows.md)
- [Configuration](./docs/configuration.md)
- [Troubleshooting](./docs/troubleshooting.md)

---

## Example

Example configuration:

```yaml
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "REPLACE_WITH_IMMICH_API_KEY"

watch:
  sources:
    - path: "C:\\Users\\YOUR_USER\\Pictures\\Screenshots"
      albumName: "Screenshots"
      includeSubdirectories: true
      extensions:
        - ".avif"
        - ".bmp"
        - ".gif"
        - ".heic"
        - ".heif"
        - ".jp2"
        - ".jpe"
        - ".jpeg"
        - ".jpg"
        - ".insp"
        - ".jxl"
        - ".png"
        - ".psd"
        - ".raw"
        - ".rw2"
        - ".svg"
        - ".tif"
        - ".tiff"
        - ".webp"
      excludeDirectories:
        - "private"
      excludeFileNames:
        - "Thumbs.db"
  batchIntervalSeconds: 5
  maxBatchSize: 25
  fileReadyTimeoutSeconds: 30

retry:
  maxAttempts: 5
  baseDelayMilliseconds: 500

logging:
  level: "Information"
  logDirectory: "C:\\Users\\YOUR_USER\\AppData\\Local\\Immich Folder Watch\\logs"
```

---

## Documentation

The Windows GUI now keeps these per-source watch options collapsed by default and only shows `Excluded Directories` when `Include subdirectories` is enabled.

- [Configuration](./docs/configuration.md)
- [Windows Installation](./docs/installation-windows.md)
- [Architecture](./docs/architecture.md)
- [Troubleshooting](./docs/troubleshooting.md)
- [Development](./docs/development.md)

---

## Contact

Issues and feature requests are welcome via GitHub Issues.
Please read [`CONTRIBUTING.md`](./CONTRIBUTING.md) first.

---

## ⭐ Support the Project

If you find the project useful, consider leaving a star on GitHub ⭐
It helps visibility and supports continued development.

---

## ⭐ Star History

<a href="https://www.star-history.com/#/VoltKraft/immich-folder-watch&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=voltkraft/immich-folder-watch&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=voltkraft/immich-folder-watch&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=voltkraft/immich-folder-watch&type=date&legend=top-left" />
 </picture>
</a>

---

## License

This repository is licensed under **AGPL-3.0-only**. See [LICENSE](./LICENSE).
