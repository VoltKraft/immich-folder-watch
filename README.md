<p align="center">
  <img src="./assets/branding/logo.svg" alt="Immich Folder Watch logo" width="128" />
</p>

# Immich Folder Watch

[![Windows: x86-64 and ARM64](https://img.shields.io/badge/Windows-x86--64%20%7C%20ARM64-0078D6?logo=windows)](./docs/installation-windows.md)
[![Linux Flatpak: x86-64 and ARM64](https://img.shields.io/badge/Linux%20(Flatpak)-x86--64%20%7C%20ARM64-FCC624?logo=linux&logoColor=black)](./packaging/flatpak/README.md)
[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](./LICENSE)

`Immich Folder Watch` connects local photo and video folders with Immich on **Windows and Linux**. Automatically upload new or existing media, or keep local folders and Immich albums synchronized with uploads and downloads. Choose the behavior separately for each folder.

This is a community desktop client maintained separately from the Immich project.

Use it to keep an Immich album available locally, organize albums through local subfolders, import a photo collection, or send new camera imports and screenshots to Immich. It runs in the background as a per-user desktop app and communicates through the Immich API without writing directly into Immich storage.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/images/ui-folders-dark.png" />
  <source media="(prefers-color-scheme: light)" srcset="./docs/images/ui-folders-light.png" />
  <img src="./docs/images/ui-folders-light.png" alt="Immich Folder Watch on Windows: the English folder editor with sample folders, album placement, and sync mode selection" width="1080" />
</picture>

*Windows interface with sample data. The preview follows your browser's color
preference; [light](./docs/images/ui-folders-light.png) and
[dark](./docs/images/ui-folders-dark.png) versions are also available directly.*

See the [illustrated desktop guide](./docs/user-interface.md) to connect Immich,
add folders, choose a sync mode, and adjust transfer and logging settings.

---

## Use Cases

- Keep a local folder synchronized with an Immich album, including photos added to Immich from other devices
- Access synchronized photos and videos locally with desktop tools, even while offline
- Map first-level subfolders to Immich albums and keep their names and media placement in sync
- Import an existing photo or video collection and continue uploading new additions
- Automatically send new screenshots, camera imports, or scans to dedicated Immich albums
- Use an upload inbox that optionally removes local files after a confirmed upload and album assignment
- Combine workflows: synchronize a `Family` album while uploading new files from `Screenshots` or `Camera Imports`


---

## How it works

Add one or more local folders and choose a **sync mode** for each:

| Mode | Local folder → Immich | Immich → local folder |
| --- | --- | --- |
| **Upload new files only** (default) | Uploads new files that appear while the app is running; existing files are ignored. | No downloads. |
| **Upload everything in the folder** | Includes existing media at startup and uploads new additions. | No downloads. |
| **Sync folder with album (bidirectional)** | Uploads missing local media and propagates tracked local deletions and moves. | Downloads missing media and removes tracked local files when their media leaves the synchronized remote scope. |

In bidirectional mode, set an album name to synchronize one album with a flat
local folder. Leave it empty to map first-level subfolders to Immich albums;
the root folder then corresponds to media outside albums. Changes arrive through
Immich's realtime connection, with polling as a fallback.

Synchronization can change both sides: deleting a tracked local file moves its
Immich asset to trash, and local folder changes can affect albums. Removing media
from the synchronized remote scope can permanently delete its tracked local copy.
Upload modes offer an optional inbox setting that permanently deletes confirmed local
uploads. Review the [sync modes and deletion behavior](./docs/user-interface.md#folders)
when choosing a workflow.

---

## Features

- Per-folder upload or bidirectional sync, with multiple workflows running together
- Local access to media downloaded from Immich, including additions from other devices
- Optional album placement for uploads; single-album or subfolders-as-albums synchronization
- Automatic album creation and synchronization of album/subfolder renames in bidirectional mode
- Per-folder media extensions and exclusion filters
- Configurable upload/download order, upload batches, and file readiness checks
- Persistent sync state shared by all watched folders, so unchanged files do not generate uploads or downloads after a restart
- Retries transient upload failures automatically
- Live connection status, upload/download progress, last successful transfer, and sync errors
- Background operation with a Windows tray icon; the Flatpak package provides an in-app background notice
- Checks GitHub Releases on startup and links to the release page when an update is available
- Autostarts on login by default; togglable in the GUI
- Verifies Immich URL, API key, and required permissions from the GUI
- Localized UI (English, German) with OS auto-detect and live in-app language switching
- Cross-platform: Windows MSI and Linux Flatpak built from the same Core; Windows logs to the Event Log by default, Linux to journald

---

## Installation

### Windows (MSI)

1. Download the matching MSI from [GitHub Releases](https://github.com/VoltKraft/immich-folder-watch/releases):
   `immich-folder-watch-<version>-win-x64.msi` for Intel/AMD Windows or
   `immich-folder-watch-<version>-win-arm64.msi` for Windows on Arm.
2. Install it with administrative rights (per-machine binary install).
3. Open the `Immich Folder Watch` desktop shortcut.
4. Open **Connection**, enter your Immich URL and API key, and review the verification result.
5. Open **Folders**, add your sources, and choose each folder's upload or bidirectional sync mode under **General**. Review its album, file filters, and deletion behavior in the [desktop interface guide](docs/user-interface.md). Set the global upload/download order under **Settings → Transfer**; newest files are processed first by default.
6. **Save and Apply** — transfers and folder monitoring start with the selected modes.

Each Windows user has their own configuration. The app autostarts at login by default.
`winget install VoltKraft.ImmichFolderWatch` selects the matching x64 or ARM64
installer automatically once a multi-architecture release is published. Releases
through `v2.7.0` remain x64-only and are not backfilled.

Installed layout:

- Binaries: `%ProgramFiles%\Immich Folder Watch\bin\` (shared, per-machine)
- Config: `%LOCALAPPDATA%\Immich Folder Watch\config.yaml` (per user)
- Sync state: `%LOCALAPPDATA%\Immich Folder Watch\sync-state.db` (one shared database per user)
- Logs: Windows Event Log (`Immich Folder Watch` source, default) or `%LOCALAPPDATA%\Immich Folder Watch\logs\` when File logging is selected
- Autostart: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Immich Folder Watch.lnk`

Upgrading from an older service-based install: the legacy service is stopped and removed, and the existing `C:\ProgramData\Immich Folder Watch\config.yaml` is migrated into the installing user's `%LOCALAPPDATA%`.

### Linux (Flatpak)

1. Download the matching bundle from
   [GitHub Releases](https://github.com/VoltKraft/immich-folder-watch/releases):
   `immich-folder-watch-<version>-linux-x64.flatpak` on `x86_64` or
   `immich-folder-watch-<version>-linux-arm64.flatpak` on `aarch64`.
2. Install and launch it for the current user:

```bash
flatpak install --user ./immich-folder-watch-<version>-linux-<architecture>.flatpak
flatpak run io.github.voltkraft.immich-folder-watch
```

Flatpak assets are published by the current release workflow; `v2.7.0` and
earlier releases are not backfilled.

GitHub's single-file bundle records Flathub as the source for its Freedesktop
runtime dependency, but it does not configure an application repository.
Download each new application version manually and install it with
`flatpak install --user --or-update ./immich-folder-watch-<version>-linux-<architecture>.flatpak`.
Flathub release automation is prepared; initial acceptance is still pending. See
[`the Flathub preparation guide`](./packaging/flatpak/flathub/README.md) for status and
[`packaging/flatpak/README.md`](./packaging/flatpak/README.md) for local builds.

The Flatpak package runs through X11/XWayland because the current Avalonia
Linux backend initializes X11. Its tray uses the application's own D-Bus
namespace and supports KDE Plasma and GNOME with an AppIndicator extension.
When no tray host is available, the app shows a banner and remains reachable
through the launcher or Background Apps.

Sandbox layout:

- App ID: `io.github.voltkraft.immich-folder-watch`
- Config: `~/.var/app/io.github.voltkraft.immich-folder-watch/config/immich-folder-watch/config.yaml`
- Sync state: `~/.var/app/io.github.voltkraft.immich-folder-watch/config/immich-folder-watch/sync-state.db`
- Logs: journald (default — `journalctl --user -t io.github.voltkraft.immich-folder-watch.desktop`) or the directory shown under **Settings → Logging** when File logging is selected
- Autostart: requests desktop approval once during first setup; managed via the Background portal and the GUI toggle

Folder picking goes through the FreeDesktop FileChooser portal so the app only sees the folders you explicitly grant. The watcher resolves the doc-portal handles back to host paths via `org.freedesktop.portal.Documents`, and inotify-blind FUSE mounts are covered by a 5-second polling sweep.

The app keeps one automatically managed `sync-state.db` beside `config.yaml` for
all watched folders. On the first start after this database is introduced, it
performs a mode-appropriate reconciliation and records confirmed transfers.
Later starts reconcile file metadata in the background; files whose size and UTC
modification time are unchanged are not hashed, uploaded, or downloaded.

Detailed guides:

- [Windows Installation](./docs/installation-windows.md)
- [Linux Installation](./docs/installation-linux.md)
- [Linux Flatpak packaging](./packaging/flatpak/README.md)
- [Configuration](./docs/configuration.md)
- [Troubleshooting](./docs/troubleshooting.md)

---

## Example

One configuration can combine different workflows. This example uploads new
screenshots, imports an existing camera folder, and synchronizes a local folder
with the `Family` album, including media added to that album from other devices.
Deleting tracked local files or removing media from the `Family` album can also
remove the corresponding copies on the other side.

```yaml
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "REPLACE_WITH_IMMICH_API_KEY"

watch:
  sources:
    - path: "C:\\Users\\YOUR_USER\\Pictures\\Screenshots"
      albumName: "Screenshots"
      syncMode: "uploadNew"
      deleteAfterUpload: false
      includeSubdirectories: true
      extensions: [".png", ".jpg"]
    - path: "C:\\Users\\YOUR_USER\\Pictures\\Camera Imports"
      albumName: "Camera Imports"
      syncMode: "uploadAll"
      extensions: [".jpg", ".jpeg", ".heic", ".mp4"]
    - path: "C:\\Users\\YOUR_USER\\Pictures\\Family"
      albumName: "Family"
      syncMode: "sync"
      extensions: [".jpg", ".jpeg", ".heic", ".png", ".mp4"]
  transferOrder: "newestFirst" # newestFirst (default) | oldestFirst
```

See [Configuration](./docs/configuration.md) for all settings, defaults, and
the additional API permissions required for bidirectional sync.

---

## Documentation

Start with the illustrated guide to choose a workflow and configure folders.
The configuration reference explains album mapping, file selection, transfer
settings, and deletion behavior for each mode.

- [Illustrated desktop guide](./docs/user-interface.md)
- [Configuration](./docs/configuration.md)
- [Windows Installation](./docs/installation-windows.md)
- [Linux Flatpak packaging](./packaging/flatpak/README.md)
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
