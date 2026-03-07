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

## Windows Service Bundle

Build a distributable bundle with published binaries plus install scripts:

```powershell
.\packaging\windows\build-installer.ps1
```

This creates `artifacts\windows\immich-folder-watch-win-x64\`.

## Install as a Service

Open an elevated PowerShell prompt inside the generated bundle and run:

```powershell
.\install-service.ps1
```

Recommended first install:

```powershell
.\install-service.ps1 -StartupType Manual
notepad "${env:ProgramFiles}\Immich Folder Watch\config.yaml"
Start-Service ImmichFolderWatch
```

For unattended deployment with a prepared config:

```powershell
.\install-service.ps1 -StartupType Automatic -StartService
```

## Uninstall

```powershell
.\uninstall-service.ps1
```

By default, `config.yaml` and the `logs\` folder under `%ProgramFiles%\Immich Folder Watch` are preserved. Pass `-RemoveData` if you want a full cleanup.
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

- Installs binaries into `%ProgramFiles%\Immich Folder Watch`
- Creates `%ProgramFiles%\Immich Folder Watch\config.yaml` from the example config on first install
- Registers the `ImmichFolderWatch` Windows service
- Preserves `config.yaml` and `logs\` on uninstall

After the MSI install, edit the config and start the service manually the first time:

```powershell
notepad "C:\Program Files\Immich Folder Watch\config.yaml"
Start-Service ImmichFolderWatch
```
