# Development

## Build

```bash
dotnet restore
dotnet build ImmichFolderWatch.sln -c Debug
```

The app build generates branding assets automatically from `assets/branding/logo.svg`
into `artifacts/branding/`.

## Test

```bash
dotnet test ImmichFolderWatch.sln -c Debug
```

## Run

```bash
dotnet run --project src/ImmichFolderWatch.App
```

The app reads its config from `%LOCALAPPDATA%\Immich Folder Watch\config.yaml`. Use the GUI's **Save and Apply** to write it.

## CI

- `ci.yaml`: cross-platform build + test coverage for the codebase
- `release.yaml`: build the Windows MSI and Linux `x86_64` Flatpak from the
  same immutable commit, then publish both only after successful CI on `main`
  and only when the version tag does not already exist
- `winget.yaml`: submit WinGet package updates for published releases after the initial manual bootstrap has been completed
- `packaging/flatpak/`: the shared Flatpak manifest, metadata, local-build
  instructions, and postponed Flathub submission material

## Project Conventions

- Keep user-facing logs in English.
- Keep comments concise and in English.
- Avoid coupling watcher/worker orchestration with HTTP details.
- Keep Core project free of runtime host concerns.
