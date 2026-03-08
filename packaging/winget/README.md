# WinGet Packaging

This directory contains the repository-owned metadata and operator notes for the planned WinGet package:

- `PackageIdentifier`: `VoltKraft.ImmichFolderWatch`
- `PackageName`: `Immich Folder Watch`
- `Publisher`: `VoltKraft`
- `Moniker`: `immich-folder-watch`

## Current State

The repository is prepared for WinGet, but the package is not publicly installable through `winget` until the first submission to `microsoft/winget-pkgs` has been accepted.

## One-Time Bootstrap

1. Publish release `1.1.0` so the MSI is available on GitHub Releases.
2. On a Windows machine, install `wingetcreate`.
3. Run:

```powershell
wingetcreate new "https://github.com/VoltKraft/immich-folder-watch/releases/download/v1.1.0/immich-folder-watch-1.1.0-win-x64.msi" --submit
```

4. Use the metadata from `package.metadata.json` when `wingetcreate` prompts for package details.
5. After the pull request to `microsoft/winget-pkgs` is merged, set `automationEnabled` in `package.metadata.json` to `true` and add the repository secret `WINGETCREATE_TOKEN`.

## Automated Updates

After bootstrap, the GitHub Actions workflow `winget.yaml` can submit package updates automatically for later releases.
