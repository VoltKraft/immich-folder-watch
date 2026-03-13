# WinGet Packaging

This directory contains the repository-owned metadata and operator notes for the WinGet package:

- `PackageIdentifier`: `VoltKraft.ImmichFolderWatch`
- `PackageName`: `Immich Folder Watch`
- `Publisher`: `VoltKraft`
- `Moniker`: `immich-folder-watch`

## Current State

The package `VoltKraft.ImmichFolderWatch` is already published in `microsoft/winget-pkgs`.

This repository now owns the metadata and automation used to submit later package updates. End users only receive a new version through `winget` after the corresponding `microsoft/winget-pkgs` pull request has been validated and merged.

## Repository Setup

1. Create a repository secret named `WINGETCREATE_TOKEN`.
2. Use a GitHub classic personal access token that can submit pull requests to public repositories. For `wingetcreate`, `public_repo` is the relevant scope.
3. Keep `automationEnabled` in `package.metadata.json` set to `true`.

## One-Time Catch-Up To `1.5.0`

1. Open the GitHub Actions workflow `WinGet`.
2. Run the workflow manually with `release_tag` set to `v1.5.0`.
3. Wait for the automation to submit the WinGet update for:

```text
https://github.com/VoltKraft/immich-folder-watch/releases/download/v1.5.0/immich-folder-watch-1.5.0-win-x64.msi
```

4. Monitor the resulting pull request in `microsoft/winget-pkgs` until it is merged.

## Automated Updates

After the `1.5.0` catch-up submission, later published GitHub releases trigger `.github/workflows/winget.yaml` automatically and submit the next WinGet update PR.

Use the manual `release_tag` input again if a release needs to be resubmitted or backfilled.
