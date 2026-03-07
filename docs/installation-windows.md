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
notepad "$env:ProgramData\ImmichFolderWatch\config.yaml"
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

By default, configuration and logs under `%ProgramData%\ImmichFolderWatch` are preserved. Pass `-RemoveData` if you want a full cleanup.

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
- Creates `%ProgramData%\ImmichFolderWatch\config.yaml` from the example config on first install
- Registers the `ImmichFolderWatch` Windows service
- Preserves `config.yaml` on uninstall

After the MSI install, edit the config and start the service manually the first time:

```powershell
notepad C:\ProgramData\ImmichFolderWatch\config.yaml
Start-Service ImmichFolderWatch
```
