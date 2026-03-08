# immich-folder-watch

[![CI](https://img.shields.io/badge/CI-pending-lightgrey?logo=githubactions)](./.github/workflows/ci.yaml)
[![Version](https://img.shields.io/badge/Version-1.2.2-blue)](./CHANGELOG.md)
[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](./LICENSE)

`immich-folder-watch` is a Windows service with a desktop configuration app for people who want local folders to feed new files into Immich automatically.

It watches one or more folders, waits until newly written files are stable, and uploads them through the Immich HTTP API. This keeps uploads inside Immich's normal ingestion path instead of copying files directly into storage.

## What It Does

- Watches one or more local folders for new media files
- Waits for files to finish writing before upload
- Uploads new files to Immich in batches
- Assigns uploads to the configured album name per watched source
- Retries transient upload failures automatically
- Runs as a Windows service with logs and config kept on disk
- Ships a GUI to edit config, show the current app version, verify Immich URL/API key/permissions, auto-refresh service state, save and start or restart the service, start/stop/restart the service, adjust the log folder, and open logs quickly

## What It Does Not Do

- It is **not** a sync client like Nextcloud
- It does **not** mirror folders or propagate deletions
- It does **not** backfill files that already existed before the service started
- It does **not** write directly into Immich storage

The intended model is simple: leave the service running, drop new screenshots or camera imports into watched folders, and let it upload them to Immich.

## Install on Windows

The supported install path today is the Windows MSI from the GitHub Releases page.

1. Download the latest `.msi` from Releases.
2. Install it with administrative rights.
3. Open the installed `Immich Folder Watch` desktop shortcut.
4. Review the automatic Immich access check in the GUI, then edit the config and use **Save and Start**.

The MSI installs the service in the **Manual** state first. Updates also normalize previously disabled installs back to **Manual** so the GUI and admin helper can start the service again. The GUI auto-refreshes the displayed service state, shows the app version in the header, keeps `logging.logDirectory` on an absolute path, runs a one-time access check for the configured Immich URL, API key, and required permissions, and uses **Save and Start** or **Save and Restart** to apply the config. Any GUI-triggered start or restart switches the service to **Automatic (Delayed Start)** unless the service is already configured as **Automatic** without delay.

Detailed setup instructions:
- [Windows Installation](./docs/installation-windows.md)
- [Configuration](./docs/configuration.md)
- [Troubleshooting](./docs/troubleshooting.md)

## Example Use Cases

- Automatically upload screenshots into an Immich album
- Watch an import folder used by another tool or device sync
- Keep a small always-on Windows host pushing new media into Immich

## Distribution

- MSI releases are the current supported installation method
- The repository is prepared for a future WinGet package under `VoltKraft.ImmichFolderWatch`
- The first WinGet community submission still has to be completed before `winget install` becomes publicly available

## Documentation

- [Configuration](./docs/configuration.md)
- [Windows Installation](./docs/installation-windows.md)
- [Architecture](./docs/architecture.md)
- [Linux Status](./docs/installation-linux.md)
- [Development](./docs/development.md)

## License

This repository is licensed under **AGPL-3.0-only**. See [LICENSE](./LICENSE).
