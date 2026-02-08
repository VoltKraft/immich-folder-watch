# Installation on Windows

## Prerequisites

- Windows 10/11 or Windows Server
- .NET SDK 8.0+ (for source-based run/build)
- Immich server URL and API key

## Console Mode

```powershell
copy examples\config.example.yml config.yml
# Edit config.yml

dotnet restore
dotnet build ImmichFolderWatch.sln -c Release
dotnet run --project src/ImmichFolderWatch.Daemon -- --config config.yml
```

## Windows Service (Notes)

Service packaging is planned. Current recommendation:

- Publish a self-contained daemon build.
- Install using your preferred service wrapper (for example `sc.exe`, NSSM, or enterprise tooling).
- Pass `--config <path>` in service start arguments.

Packaging stubs live under `packaging/windows`.
