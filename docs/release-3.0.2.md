# Release v3.0.2 verification

## Scope and preparation

Selected on 2026-11-11 by explicit user authorization to publish all new main
changes. Baseline: `8d7afba43d51d80021c28862a2ec94802eb83c17`. PR #32 remains
excluded and license-blocked; automatic merging remains disabled.

This compatible maintenance release includes the YAML string-preservation fix,
reviewed SocketIO transport/shutdown adaptation, build-tool and dependency
updates, Dependabot correction and all maintenance evidence since v3.0.1.
No configuration or persistent-data migration is introduced. Existing 3.0.0
HTTPS-by-default requirements remain unchanged.

Version preparation follows the repository bump script and AppStream generator.
[Semantic Versioning 2.0.0](https://semver.org/) and
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) were checked against
their official sites on 2026-11-11. Versions: 3.0.2 / 3.0.2.0.

## Validation and publication

Local checks pass: exact version/changelog/AppStream assertions, AppStream
validation without network, five manifest tests and six workflow-security tests.
Four PowerShell-specific tests skipped locally subsequently passed in Windows CI.
Independent review
confirms complete release notes, preserved historical entries and unchanged
product/workflow content; a Windows-only note was excluded from Linux metadata.
Hosted CI/CodeQL, four release builds and publication have succeeded. The release
workflow created the immutable tag after all four artifacts built successfully.
No live Immich connection or application installation was performed.

## Published revision and public assets

[Stable v3.0.2](https://github.com/VoltKraft/immich-folder-watch/releases/tag/v3.0.2)
was published at 2026-11-11 13:31:22 UTC (14:31:22 CET). It is the latest stable
release, neither draft nor prerelease. The immutable tag points directly to
`df4839852bb84efef35a83cc429d51ce55b9ed1e`, containing all baseline main changes
and the reviewed release metadata. Public notes exactly match the changelog.

Downloaded all four assets from their public URLs; exact bytes and SHA-256 hashes
match GitHub's asset metadata:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `immich-folder-watch-3.0.2-linux-arm64.flatpak` | 30488160 | `62afbc19fdb0f15618ae93b1187a4dd24ffc76d69d1b48e8eb9057fbd7a63744` |
| `immich-folder-watch-3.0.2-linux-x64.flatpak` | 33622880 | `dd74834e1e9253ae3706b747d5f6d4e6c658961b8466b48cff8bc2fdbcd9ecc6` |
| `immich-folder-watch-3.0.2-win-arm64.msi` | 49446847 | `7a62fa7aef734b9252b2296640d82407c7eb73936ac9a8afee24f58449b43756` |
| `immich-folder-watch-3.0.2-win-x64.msi` | 54849590 | `c33ef793b095d0060745b824107332258f286a096b57383d04109804231a8b4d` |

## Hosted validation

All runs target the release commit `df48398`:

| Workflow | Result |
| --- | --- |
| [CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43028337410) | All eight jobs passed, including Windows/Linux tests, native Flatpak builds and Pages artifact round trips. |
| [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43028337532) | All four language analyses passed. |
| [NuGet submission](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43028337394) | Passed. |
| [Release](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43029241209) | All nine jobs passed: four packages, complete asset verification, tag/publication and downstream dispatches. |
| [Flatpak repository](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43029896872) | Both signed-repository build and Pages deployment passed. |
| [WinGet](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43029894028) | Submitted [microsoft/winget-pkgs#477568](https://github.com/microsoft/winget-pkgs/pull/477568); open, not merged at verification. |
| [Flathub](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43029893067) | Preparation and both native builds passed; update submission was skipped because automation remains disabled. |

Linux passes all 501 Core and 53 Linux tests. Windows passes 36 Windows,
492 Core and 34 Linux-portable tests; nine Core and 19 Linux-specific tests are
platform-skipped there and exercised on Linux. All ten workflow-security tests
run successfully on Windows. Open CodeQL and Dependabot alert counts are zero.

## Public signed Flatpak source

The public index, `.flatpakrepo`, `.flatpakref` and key are reachable. Descriptor
keys match the published key and the tracked signing identity
`4ED65AC1C14D559C721C7A8B44B33451708EAD7D`. An isolated OSTree client with both
`gpg-verify=true` and `gpg-verify-summary=true` successfully pulled each stable
architecture's metainfo; both report 3.0.2. No installed application or personal
Flatpak remote was changed.

| Architecture | Verified stable `master` commit |
| --- | --- |
| x86_64 | `7b45da85328ab855c389ad30e14ca45163409c99227cab0fd16ab3b5d177dd72` |
| aarch64 | `694243ec8f7a8eb521cfd4eac6b9a749cdb54dda897b7adfe441add22865086a` |

## Boundaries and follow-up

#32 remains open/license-blocked at `51898a8`; it is excluded from this release.
Repository auto-merge remains disabled, and no PR auto-merge was activated.
External WinGet acceptance and Flathub onboarding are distinct from the completed
GitHub/Pages publication. Final evidence is saved in a local documentation checkpoint after the release
tag; it is not pushed and does not alter published source or artifacts. Remote
main and v3.0.2 remain at `df48398`; v3.0.1 remains unchanged at `1ab0748`.
Release publication and validation are complete. No further release work is
required; external WinGet acceptance and optional Flathub onboarding remain
separate follow-up items.
