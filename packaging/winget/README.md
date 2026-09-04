# WinGet Packaging

This directory contains the repository-owned metadata and operator notes for the WinGet package:

- `PackageIdentifier`: `VoltKraft.ImmichFolderWatch`
- `PackageName`: `Immich Folder Watch`
- `Publisher`: `VoltKraft`
- `Moniker`: `immich-folder-watch`

## Current State

The package `VoltKraft.ImmichFolderWatch` is already published in `microsoft/winget-pkgs`.

This repository now owns the metadata and automation used to submit later package updates. End users only receive a new version through `winget` after the corresponding `microsoft/winget-pkgs` pull request has been validated and merged.

Future submissions contain two native WiX installers under the same package
identifier. WinGet selects `x64` on Intel/AMD Windows and `arm64` on Windows on
Arm. Releases through `v2.7.0` remain unchanged and are not backfilled.

## Repository Setup

1. Create a repository secret named `WINGETCREATE_TOKEN`.
2. Use a GitHub classic personal access token that can submit pull requests to public repositories. For `wingetcreate`, `public_repo` is the relevant scope.
3. Keep `automationEnabled` in `package.metadata.json` set to `true`.

## Automated Updates

After all four GitHub release artifacts have been published,
`.github/workflows/winget.yaml`:

1. Resolves the published release by its immutable tag.
2. Requires exactly one x64 and one ARM64 MSI matching the templates in
   `package.metadata.json`.
3. Downloads both MSIs and extracts their SHA-256 hashes and MSI ProductCodes.
4. Calls `tools/prepare-winget-release-manifests.py` to create a complete
   multi-file manifest with both installer nodes.
5. Uses `wingetcreate submit` to validate the manifest and open the update pull
   request in `microsoft/winget-pkgs`.

The workflow fails without submitting anything when either MSI is missing or
its metadata is invalid. Monitor the resulting pull request until it is merged;
only then is the new version available to end users through WinGet.

The internal manifest-generator interface is:

```text
prepare-winget-release-manifests.py --metadata <json> --installers <json> --output-dir <dir> --version <MAJOR.MINOR.PATCH> --release-date <YYYY-MM-DD>
```

The installer JSON must contain exactly one `x64` and one `arm64` object, each
with `architecture`, `url`, `sha256`, and `productCode`. URLs must match the
release asset templates; hashes and MSI ProductCodes are validated before any
manifest is written.

## Manual Resubmission

Open the `WinGet` workflow and supply an existing published `release_tag`, for
example `v2.8.0`. The workflow checks out that tag and regenerates both
architecture entries from the release assets.

Do not use this to backfill `v2.7.0` or earlier releases because those releases
do not contain the required ARM64 MSI.
