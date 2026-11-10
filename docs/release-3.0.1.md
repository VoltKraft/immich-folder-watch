# Release v3.0.1 verification

Verified on 2026-11-11 (Europe/Berlin). The user authorized release creation and
publication with all current main changes, excluding open PRs #32 and #34.

## Published revision and artifacts

- [Stable release](https://github.com/VoltKraft/immich-folder-watch/releases/tag/v3.0.1)
  published at 00:43:06 CET on 2026-11-11 (23:43:06 UTC on 2026-11-10).
- Tag `v3.0.1` points directly to `1ab074841c76b2493dc3af5d972ce229e5746edb`,
  the verified remote main revision. It includes baseline `bb13a33`, preparation
  `b475dda`, and the scoped container-ownership correction `1ab0748`.
- The release is neither draft nor prerelease and is GitHub's latest stable
  release. Versions are 3.0.1 / 3.0.1.0; AppStream is dated 2026-11-11.
- Downloaded every asset through its public release URL; exact byte counts and
  SHA-256 hashes match GitHub's uploaded-asset metadata. No application installation
  or live Immich operation was performed.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `immich-folder-watch-3.0.1-linux-arm64.flatpak` | 30453064 | `60626b37be4581c309b5c21b4e0f7377cdcac1530a4dd2838ee458e4e4cef451` |
| `immich-folder-watch-3.0.1-linux-x64.flatpak` | 33596088 | `3d986837b0083852fc278b9a8c2824a3873cd98c33ae885ce4d9df715b61d65b` |
| `immich-folder-watch-3.0.1-win-arm64.msi` | 49434668 | `822ac7178825f710dd10820bdc45b6e0df22d8f788f740734cf8181c27f450c5` |
| `immich-folder-watch-3.0.1-win-x64.msi` | 54837411 | `d259ff4cfd14fba21339aa4158dbcbcaff0634c8b4bec355589b0d4b7825c428` |

## Hosted validation

All results below apply to commit `1ab0748`:

| Workflow | Result |
| --- | --- |
| [CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42924215573) | Six jobs passed: Windows/Linux builds/tests, packaging lint/preparation, native x86_64/aarch64 Flatpak candidates. |
| [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42924215424) | All four language analyses passed; open code-scanning alert count is zero. |
| [Release](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42925003749) | Both Windows MSIs and both Linux Flatpaks built successfully; complete asset set, immutable tag and publication succeeded. |
| [NuGet dependency submission](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42924214927) | Passed. |
| [Flatpak repository](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42925660723) | Signed repository build and Pages deployment passed. |
| [WinGet](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42925660421) | Submitted [microsoft/winget-pkgs#477025](https://github.com/microsoft/winget-pkgs/pull/477025); external PR remains open, acceptance is not claimed. |
| [Flathub](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42925663217) | Preparation and both architecture builds passed; update submission skipped because automation remains disabled. |

The first release attempt at `b475dda` failed before publication because Git's
ownership check rejected the new inline SHA guard inside the container. The fix
trusts only `GITHUB_WORKSPACE` for one Git command, retains SHA equality, and has a
regression that reproduces ownership rejection without a broad/global exception.
Fresh full CI and the successful release exercised the correction; no released
version or tag was replaced.

## Live Flatpak distribution

Fetched the public index, `.flatpakrepo` and `.flatpakref` successfully. An isolated
OSTree client imported only the tracked public signing key and required both
`gpg-verify=true` and `gpg-verify-summary=true`. Pulling each architecture's
metainfo succeeded with signed summary/commit verification; both report 3.0.1.

| Stable ref architecture | Verified OSTree commit |
| --- | --- |
| x86_64 | `f5c8b1d755265cf85d6081c7122979b50dade3f83835c022ffd77e4b102ddab0` |
| aarch64 | `e7f8993d2a33b8633fed19c2680a584f54e70eb711069be957f4833077915647` |

The `master` Flatpak branch and signing identity are preserved. No personal
Flatpak remotes or installed applications were changed for verification.

## Boundaries

PR #32 stays open/blocked; PR #34 stays open/deferred. Neither was merged or
modified. Repository `allow_auto_merge` is false and both PRs have `auto_merge:
null`. Release publication is complete; external WinGet acceptance and Flathub
onboarding remain separate. Final evidence documentation is a local checkpoint
after the release tag, not an alteration of the published source or artifacts.
