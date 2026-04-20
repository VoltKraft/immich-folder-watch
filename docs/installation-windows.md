# Installation on Windows

## Prerequisites

- Windows 10/11 or Windows Server
- .NET SDK 10.0+ (only for source-based builds / development)
- Immich server URL and API key

## Recommended: MSI Installer

Download the latest `.msi` from [GitHub Releases](https://github.com/VoltKraft/immich-folder-watch/releases) and run it with administrative rights. The installer is per-machine (binaries only); each Windows user keeps their own configuration and logs under `%LOCALAPPDATA%`.

After install:

1. Open the `Immich Folder Watch` desktop shortcut (or launch it from the Start menu).
2. Enter your Immich URL and API key, then review the verification result.
3. Select one or more folders. Expand **Advanced Watch Options** only if you want to adjust subdirectories, extensions, or exclude filters.
4. Click **Save and Apply** — the app starts watching in-process and a tray icon appears in the notification area.

### Installed Layout

- `%ProgramFiles%\Immich Folder Watch\bin\` — app binaries (per-machine)
- `%LOCALAPPDATA%\Immich Folder Watch\config.yaml` — per-user active config
- `%LOCALAPPDATA%\Immich Folder Watch\logs\` — per-user app logs
- `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Immich Folder Watch.lnk` — autostart shortcut (default on; togglable in the GUI)

### Autostart and Tray Behavior

- Closing the main window hides it to the tray; the app keeps watching in the background.
- The tray icon's tooltip shows last sync time, queue length, and server connection.
- The tray context menu provides **Open GUI**, **Restart**, and **Quit**.
- Disable autostart via the **Start at login** checkbox in the GUI.

### Uninstall

`msiexec /x <package>.msi` (or uninstall from Settings → Apps). The installer removes binaries and the desktop shortcut but **preserves** `%LOCALAPPDATA%\Immich Folder Watch\` so your config and logs stay intact.

The autostart shortcut stays behind as a dead link; delete it manually from `shell:startup` if desired.

## Upgrade From Older Service-Based Installs

Versions ≤ 1.6.x installed a Windows service (`ImmichFolderWatch`) with a shared config under `C:\ProgramData\Immich Folder Watch\`. When you upgrade via the new MSI:

1. The legacy service is stopped and deleted.
2. The existing `C:\ProgramData\Immich Folder Watch\config.yaml` is copied into the **installing user's** `%LOCALAPPDATA%\Immich Folder Watch\config.yaml` (only if that user does not already have one).
3. The `C:\ProgramData\Immich Folder Watch\` folder is removed.
4. Autostart is enabled for the installing user.

Other Windows users on the same machine need to launch the app once to seed their own per-user config — they do not inherit the migrated settings.

## Multi-User Setup

Every Windows user can run the app with their own watch folders and Immich credentials. The per-user config isolation means:

- Each user's API key is stored only under their own profile.
- Logs are not shared across users.
- Running the app simultaneously under two logged-in accounts is supported (each instance has its own single-instance mutex scoped to the user SID).

## Building From Source

```powershell
dotnet restore
dotnet build ImmichFolderWatch.sln -c Release
dotnet run --project src/ImmichFolderWatch.App
```

## Building the MSI Locally

```powershell
.\packaging\windows\build-msi.ps1
```

The MSI is produced under `artifacts\windows\msi\`. On the first run, `dotnet` restores the WiX SDK from NuGet.
