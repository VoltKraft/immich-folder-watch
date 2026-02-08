# Development

## Build

```bash
dotnet restore
dotnet build ImmichFolderWatch.sln -c Debug
```

## Test

```bash
dotnet test ImmichFolderWatch.sln -c Debug
```

## Run

```bash
dotnet run --project src/ImmichFolderWatch.Daemon -- --config config.yaml
```

## CI

- `ci.yaml`: build + test on Windows and Linux
- `release.yaml`: publish artifacts and draft release on tag
- `flatpak-build.yaml`: placeholder validation workflow

## Project Conventions

- Keep user-facing logs in English.
- Keep comments concise and in English.
- Avoid coupling daemon orchestration with HTTP details.
- Keep Core project free of runtime host concerns.
