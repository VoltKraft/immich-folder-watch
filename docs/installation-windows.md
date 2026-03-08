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
- `%ProgramFiles%\Immich Folder Watch\config\config.yaml`
- `%ProgramFiles%\Immich Folder Watch\config\activation-state.json`
- `%ProgramFiles%\Immich Folder Watch\logs\`

If an older Windows install still uses `%ProgramFiles%\Immich Folder Watch\config.yaml`, the bundle installer and MSI migrate it to `config\config.yaml` automatically when the new path does not exist yet.
If both files already exist, `config\config.yaml` stays active and the legacy root-level file is left untouched.

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

The GUI edits `%ProgramFiles%\Immich Folder Watch\config\config.yaml`, verifies the config against Immich, then enables `Automatic (Delayed Start)` and starts the service on the first successful save.
The GUI also refreshes service status automatically and keeps `logging.logDirectory` on an absolute path. Use **Use Install Default** if you want to reset logs to `%ProgramFiles%\Immich Folder Watch\logs`.

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

By default, the `config\` and `logs\` folders under `%ProgramFiles%\Immich Folder Watch` are preserved. Pass `-RemoveData` if you want a full cleanup.
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
- Creates `%ProgramFiles%\Immich Folder Watch\config\config.yaml` from the Windows installer template on first install
- Stores GUI activation state in `%ProgramFiles%\Immich Folder Watch\config\activation-state.json`
- Creates `%ProgramFiles%\Immich Folder Watch\logs\`
- Migrates a legacy root-level `config.yaml` into `config\config.yaml` when needed
- Registers the `ImmichFolderWatch` Windows service as `Manual`
- Preserves the current service startup mode across upgrades, except that previously disabled installs are normalized to `Manual`
- Creates a desktop shortcut for the GUI
- Preserves `config\` and `logs\` on uninstall

After the MSI install, open the GUI from the desktop shortcut and use **Save And Verify**:

```powershell
"C:\Program Files\Immich Folder Watch\bin\ImmichFolderWatch.Gui.exe"
```

The status panel refreshes automatically while the GUI is open, and the log-folder field is stored as an absolute path.
