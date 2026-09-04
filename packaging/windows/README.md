# Windows Packaging

This directory contains the automation-friendly Windows packaging flow.

## Included

- `build-msi.ps1`: publishes `ImmichFolderWatch.App` and builds an `.msi` installer with WiX
- `config.windows.example.yaml`: per-user config template (for reference only, no longer embedded in the MSI)
- `ImmichFolderWatch.Setup.wixproj` / `Installer.wxs`: WiX authoring for the MSI package
- `installer.stub.md`: notes on future bootstrapper `.exe` scope

## Current Status

- Native x64 and ARM64 MSI packages are the supported end-user installation
  paths. GitHub Releases publishes both, and the shared WinGet package selects
  the matching architecture.
- A bootstrapper `.exe` is still planned.

Build either package from Windows with:

```powershell
.\packaging\windows\build-msi.ps1 -Runtime win-x64
.\packaging\windows\build-msi.ps1 -Runtime win-arm64
```

The resulting names are `immich-folder-watch-<version>-win-x64.msi` and
`immich-folder-watch-<version>-win-arm64.msi`.

## Default Layout

- `%ProgramFiles%\Immich Folder Watch\bin\`: app binaries and runtime files
- `%LOCALAPPDATA%\Immich Folder Watch\config.yaml`: per-user active config
- `%LOCALAPPDATA%\Immich Folder Watch\logs\`: per-user app logs
- `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Immich Folder Watch.lnk`: autostart shortcut (default on)

Each Windows user has an independent config and log directory. The app runs as a user-context process (tray icon + optional main window). No Windows service is installed.

## Upgrade From Legacy Service Installs

When upgrading from a version that installed the `ImmichFolderWatch` Windows service:

- The legacy service is stopped and deleted.
- The existing `C:\ProgramData\Immich Folder Watch\config.yaml` is copied to the installing user's `%LOCALAPPDATA%\Immich Folder Watch\config.yaml` (only for the account running the MSI).
- The `C:\ProgramData\Immich Folder Watch\` folder is removed.
- Autostart is enabled by default.

Other Windows users on the same machine keep using the app after their first launch, which seeds a fresh per-user config.
