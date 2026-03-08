# Installation on Windows

## Prerequisites

- Windows 10/11 or Windows Server
- .NET SDK 10.0+ (for source-based run/build)
- Immich server URL and API key

## Console Mode

```powershell
copy examples\config.example.yaml config.yaml
# Edit config.yaml

dotnet restore
dotnet build ImmichFolderWatch.sln -c Release
dotnet run --project src/ImmichFolderWatch.Daemon -- --config config.yaml
```

## Windows Service Bundle (Advanced / Internal)

Build a distributable bundle with published binaries plus install scripts:

```powershell
.\packaging\windows\build-installer.ps1
```

This creates `artifacts\windows\immich-folder-watch-win-x64\`.

This bundle is mainly for development, recovery, or unattended internal deployment. The supported end-user installation path remains the MSI package.

Installed layout:

- `%ProgramFiles%\Immich Folder Watch\bin\`
- `C:\ProgramData\Immich Folder Watch\config.yaml`
- `C:\ProgramData\Immich Folder Watch\logs\`

If an older Windows install still uses `%ProgramFiles%\Immich Folder Watch\config\config.yaml` or `%ProgramFiles%\Immich Folder Watch\config.yaml`, the bundle installer and MSI migrate that config into `C:\ProgramData\Immich Folder Watch\config.yaml` automatically. Old default logs from `%ProgramFiles%\Immich Folder Watch\logs\` are moved to `C:\ProgramData\Immich Folder Watch\logs\` when the config still used the old default log path.

## Install as a Service

Open an elevated PowerShell prompt inside the generated bundle and run:

```powershell
.\install-service.ps1
```

Default behavior:

- registers the service as `Manual`
- does not start it immediately after installation

Recommended first install:

```powershell
.\install-service.ps1
"${env:ProgramFiles}\Immich Folder Watch\bin\ImmichFolderWatch.Gui.exe"
```

The GUI edits `C:\ProgramData\Immich Folder Watch\config.yaml`, masks real API keys by default while still allowing a reveal toggle, keeps the example placeholder visible in plain text, verifies the config against Immich whenever you save, then starts or restarts the service as needed.
No separate persistent activation-state file is stored anymore.
The GUI also refreshes service status automatically and keeps `logging.logDirectory` on an absolute path. Use **Use Install Default** if you want to reset logs to `C:\ProgramData\Immich Folder Watch\logs`. If you change the log directory in the GUI and save successfully, existing logs are migrated into the new location. When files with the same name already exist there, the existing target files win and conflicting old files are left in place.

If you explicitly want the script to leave the service enabled immediately:

```powershell
.\install-service.ps1 -StartupType Automatic -StartService
```

On later GUI saves, a running service is restarted automatically so the changed config is applied immediately.

For unattended deployment with a prepared config and immediate first start:

```powershell
.\install-service.ps1 -StartupType Automatic -StartService
```

## Uninstall

```powershell
.\uninstall-service.ps1
```

By default, `C:\ProgramData\Immich Folder Watch\` is preserved. Pass `-RemoveData` if you want a full cleanup of both the ProgramData data and any remaining legacy default data under `%ProgramFiles%\Immich Folder Watch`.
The script now waits for the service to actually disappear before removing files, so reinstall after uninstall is more reliable.

The packaging scripts live under `packaging/windows`.

## MSI Installer

Build a Windows Installer package:

```powershell
.\packaging\windows\build-msi.ps1
```

This creates an `.msi` under `artifacts\windows\msi\`.
On the first run, `dotnet` restores the WiX SDK from NuGet.

Installer behavior:

- Installs binaries into `%ProgramFiles%\Immich Folder Watch\bin\`
- Installs the GUI, daemon, and admin helper executables together
- Creates `C:\ProgramData\Immich Folder Watch\config.yaml` from the Windows installer template on first install
- Creates `C:\ProgramData\Immich Folder Watch\logs\`
- Migrates the old default config from `%ProgramFiles%\Immich Folder Watch\config\config.yaml` or `%ProgramFiles%\Immich Folder Watch\config.yaml` into ProgramData when needed
- Moves old default logs from `%ProgramFiles%\Immich Folder Watch\logs\` into ProgramData when the previous config still used that default path
- Registers the `ImmichFolderWatch` Windows service as `Manual`
- Preserves the current service startup mode across upgrades, except that previously disabled installs are normalized to `Manual`
- Creates a desktop shortcut for the GUI
- Preserves `C:\ProgramData\Immich Folder Watch\` on uninstall

After the MSI install, open the GUI from the desktop shortcut and use **Save and Start**:

```powershell
"C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.Gui.exe"
```

The status panel refreshes automatically while the GUI is open, the log-folder field is stored as an absolute path, and successful GUI saves migrate logs when you move `logging.logDirectory` to a new location.
