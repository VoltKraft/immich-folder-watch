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
5. Downloads `wingetcreate` **v1.12.13.0** from its versioned official release
   URL and verifies SHA-256 before executing it. A hash mismatch stops submission.
6. Uses `wingetcreate submit` to validate the manifest and open the update pull
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

## Automation trust and updates

Workflow inputs and release tags reach PowerShell through environment variables,
not generated script source. Tags must match stable `vMAJOR.MINOR.PATCH` before
checkout or workflow outputs are written. All action references are pinned to
full upstream commit IDs, and checkout does not persist Git credentials.

The pinned executable SHA-256 is
`24042BD37915805615E6CF969AC57C6439124C3FE85823327F5F3FB24BD9FFEA`.
It was verified against both the downloaded executable and the checksum published
with [Microsoft's v1.12.13.0 release](https://github.com/microsoft/winget-create/releases/tag/v1.12.13.0).
To update it, review the official release and its MIT license, independently
calculate the executable hash, then change the versioned URL and expected hash
in the same reviewed change. Do not replace them with a moving download URL or
fetch the expected checksum dynamically during the credential-bearing workflow.

`tools/tests/test_workflow_security.py` checks action/container pins and token
boundaries. With PowerShell available, it executes the actual inline tag parser
with command/output-injection payloads and verifies that a tampered executable
stops the workflow. Windows CI runs these cases before the application build.

## Manual Resubmission

Open the `WinGet` workflow and supply an existing published `release_tag`, for
example `v2.8.0`. Run the workflow from `main` so it uses the latest packaging
tooling while resolving version and installer data from the immutable release
tag. It then regenerates both architecture entries from the release assets.

Do not use this to backfill `v2.7.0` or earlier releases because those releases
do not contain the required ARM64 MSI.

## Catalog icon

The required `icon` object in `package.metadata.json` supplies the existing
512 x 512 PNG through a full-commit-pinned `raw.githubusercontent.com` URL.
Its SHA-256 binds the downloaded bytes. The generator emits `Icons` in the
default-locale manifest; installer and version manifests are unaffected.
`IconResolution` is `custom`, because schema 1.12.0 does not enumerate 512 x 512.
`IconTheme: default` makes the same transparent artwork available in both themes.

When changing branding, regenerate from `assets/branding/logo.svg`, publish the
source asset normally, then update the pinned URL and hash together. Verify the
public bytes and dimensions before submission. Do not use a moving branch URL.
The MSI's embedded Windows icon is independent of this catalog metadata.

For a metadata-only correction to an already published version, preserve the
upstream manifest set and add only the generator's `Icons` block to its existing
default-locale file. Validate all three files against the official matching
[WinGet schemas](https://github.com/microsoft/winget-cli/tree/master/schemas/JSON/manifests),
then submit a scoped PR to `microsoft/winget-pkgs`. Do not regenerate or replace
installer fields for an icon-only correction. No product version bump is needed.
Upstream acceptance and a refreshed client's actual display remain separate checks.

Generator regression tests:

```bash
python3 -m unittest discover -s tools/tests -p test_prepare_winget_release_manifests.py -v
```
