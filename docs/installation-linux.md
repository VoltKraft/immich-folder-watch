# Installation on Linux

Linux is not a supported release target in version `1.0.0`.

There is currently no maintained Linux packaging, no supported `systemd` installer flow, and no published Linux release artifact.

## Current Status

- The daemon codebase still builds cross-platform in CI.
- The supported installer and release workflow currently targets Windows only.
- Linux service packaging remains planned work, not a finished product.

## If You Still Want to Experiment

```bash
cp examples/config.example.yaml config.yaml
# Edit config.yaml

dotnet restore
dotnet build ImmichFolderWatch.sln -c Release
dotnet run --project src/ImmichFolderWatch.Daemon -- --config config.yaml
```

That manual source-based run is experimental and currently not documented as a supported Linux deployment path.
