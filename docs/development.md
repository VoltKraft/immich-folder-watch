# Development

## Build

```bash
dotnet restore
dotnet build ImmichFolderWatch.sln -c Debug
```

The app build generates branding assets automatically from `assets/branding/logo.svg`
into `artifacts/branding/`.

### Branding

The logo source is the open golden folder with a compact five-color flower. The
petals are individually rotated 6 degrees clockwise and moved toward the center;
their spacing exposes the folder color without white outlines. Its transparent
`1024 x 820` viewBox fits the artwork without an outer border or additional padding.
Keep this tight crop when editing the source: the generator preserves the aspect
ratio and centers it in square PNG and ICO frames, using their full width. The
remaining space above and below is transparent and preserves the folder's proportions.
Edit the SVG rather than generated assets. To regenerate only the branding assets:

```bash
dotnet build tools/BrandAssetGen/BrandAssetGen.csproj -c Debug
```

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
- `release.yaml`: build x64 and ARM64 Windows MSIs and Linux Flatpaks from the
  same immutable commit, then publish all four only after successful CI on
  `main` and only when the version tag does not already exist
- `winget.yaml`: generate and submit the two-architecture WinGet manifest after
  the GitHub Release has been published
- `packaging/flatpak/`: the shared Flatpak manifest, metadata, local-build
  instructions, and postponed Flathub submission material

## Project Conventions

- Keep user-facing logs in English.
- Keep comments concise and in English.
- Avoid coupling watcher/worker orchestration with HTTP details.
- Keep Core project free of runtime host concerns.
