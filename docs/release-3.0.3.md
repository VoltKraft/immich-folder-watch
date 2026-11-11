# Release v3.0.3 verification

## Scope and published revision

The user explicitly authorized merging #32, verifying main and creating the new
release. #32 merged with an expected-head guard as
`3740ce067644d65a296c21fec0812b9c10c8d25f`, preserving reviewed head `ce0b711`.
Local maintenance/release evidence was integrated without rewriting history;
conflicts affected only brief/status summaries. All previously reviewed product
changes are included.

[Stable v3.0.3](https://github.com/VoltKraft/immich-folder-watch/releases/tag/v3.0.3)
was published on 2026-11-11 at 17:45:50 UTC (18:45:50 CET). It is the latest stable
release, neither draft nor prerelease. The immutable tag points directly to
`e0d1c403f261b9c906cc3853a1b7477518b64bf6`, including release preparation `6c60d55`
and its verified test-harness correction. Public notes exactly match the changelog.

This compatible patch delivers the reduced Avalonia 12.1.6.1 component-license
remediation, D-Bus 0.94.1 alignment and SDK/offline provenance/CI fixes. No user
configuration or data migration is introduced. See the
[component audit](avalonia-component-audit-20261111.md),
[reduced-build contract](reduced-avalonia.md) and
[PR validation](dependabot-pr32-20261111.md).

Versions are 3.0.3 / 3.0.3.0, with AppStream date 2026-11-11. The repository bump
script and AppStream generator were used; exact-version/date, historical-changelog,
AppStream, five manifest tests and six local workflow-security tests passed.
Four PowerShell cases skipped locally passed in hosted Windows CI.
[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) and
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) were checked from
their official sources. Independent release review found no blocker.

## Main and exact-release validation

Merge commit `3740ce0` passed [CI 43066118171](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43066118171)
with eight jobs, [CodeQL 43066119121](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43066119121)
with four analyses and [NuGet 43066118345](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43066118345).
Its existing-version release follow-up 43067269421 correctly skipped publication.

Final runs target release commit `e0d1c40`:

| Workflow | Result |
| --- | --- |
| [CI 43069310276](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43069310276) | All eight jobs passed, including Windows/Linux and both native Flatpak architectures. |
| [CodeQL 43069309896](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43069309896) | All four language analyses passed. |
| [NuGet 43069309375](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43069309375) | Passed. |
| [Release 43070397650](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43070397650) | All nine jobs passed: four packages, asset-set validation, tag/publication and downstream dispatches. |
| [Flatpak repository 43071298434](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43071298434) | Signed repository build and Pages deployment passed. |
| [WinGet 43071296697](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43071296697) | Submitted [microsoft/winget-pkgs#477698](https://github.com/microsoft/winget-pkgs/pull/477698), open and awaiting external acceptance. |
| [Flathub 43071297173](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43071297173) | Preparation and both native validation builds passed; update submission was skipped because Flathub automation remains disabled. |

Linux passes all 503 Core and 60 Linux tests. Windows passes 494 Core, 41
Linux-portable and 36 Windows tests; nine Core and 19 Linux-specific cases are
platform-skipped there and covered on Linux. All ten workflow-security tests run
on Windows; all 147 tooling tests pass in packaging CI. Open CodeQL and Dependabot
alert counts are zero after final analysis.

## Published artifact verification

Downloaded all four assets from their public URLs. Exact sizes and SHA-256 hashes
match GitHub's release metadata:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `immich-folder-watch-3.0.3-linux-arm64.flatpak` | 30548576 | `e9a322842a81acca0dadac89fbf817b817f08b0cedc7319a33c488c1678f2224` |
| `immich-folder-watch-3.0.3-linux-x64.flatpak` | 33791512 | `fcf5d24d26343fcabfdf19d60db230cb1b33d3ecd519e7f7b45414e20b8b46f7` |
| `immich-folder-watch-3.0.3-win-arm64.msi` | 49430463 | `9fcba7f8ab01b670bc2d9580c47f46f11a81c3cabb4e8022c28fdd6eb57338d4` |
| `immich-folder-watch-3.0.3-win-x64.msi` | 54771766 | `e2559768224568eaae67db9b19b82d8390720ffb9692cfe6248f69f08042cc6c` |

Both published Linux bundles were imported into isolated OSTree repositories,
without installation. Each passes the excluded-type audit across 240 managed
assemblies with no parse failures. Reduced Controls/Fluent DLLs match the reviewed
rebuild and installed provenance byte-for-byte. Apple, SixLabors and D-Bus notices
match their reviewed source texts. Both metainfo files report 3.0.3.

- Controls SHA-256: `dd06f5e9243d3a95f45c0985a1f92c96d517e7bc746ea6d768c06125f8c08d04`
- Fluent SHA-256: `8f762376626068c2da4db11a9ece2775cd510e23c9705be7790dc28e4196c654`

Independent static MSI inspection verifies ProductName/Version 3.0.3, x64/Arm64
installer templates and matching apphost PE machine types (0x8664/0xaa64).
Each package contains 415 managed assemblies, all parsed, with no Avalonia
namespace implementations. No installer or application was executed.

## Signed public Flatpak distribution

Public index, `.flatpakrepo`, `.flatpakref` and public key are reachable. Both
descriptor keys match the unchanged tracked signing identity
`4ED65AC1C14D559C721C7A8B44B33451708EAD7D`. An isolated OSTree client with
`gpg-verify=true` and `gpg-verify-summary=true` successfully pulls stable metadata
for both architectures, reporting 3.0.3. These commits match the imported public
release bundles. No installed application or personal remote was changed.

| Architecture | Signature-verified stable master commit |
| --- | --- |
| x86_64 | `13911f50ae6efd829489d316c7cbe3251c3ea35f8e0a47e957fab6314476d2a7` |
| aarch64 | `1fb3eef7c343369658cbc89e8f12ab64d4710b5915cf2f83dc609bf420682818` |

## CI failure investigation and correction

The first release candidate `6c60d55` passed CodeQL/NuGet and seven CI jobs, but
Windows CI 43067388859 failed the existing autostart initialization test's final
busy-flag assertion. Independent review identified a test harness violation of
the documented UI-thread contract: its immediate dispatcher claimed every thread
was the UI thread, allowing async continuations to race the pending-operation
count. Reviewed production callers retain the real UI context; no corresponding
production defect was established.

A dedicated single-thread test context corrects the harness without production
changes. All 58 original assertions remain. Two additional tests check resumed/
posted callback thread identity and async exception propagation. All 19 focused
tests and 503 Core tests pass without local skips; a scratch stress runner passed
1,000 repetitions each of initialization with queued disable, concurrent changes
and queued initialization cancellation (3,000 complete scenarios). Independent
review accepted the correction. The failed candidate was never tagged/published;
the fresh exact-head CI/CodeQL results above gate the published release.

## Boundaries and follow-up

#32 is merged; repository auto-merge remains false and no automatic merge request
was enabled. Existing v3.0.2 tag `df48398` and all four asset digests were rechecked
and remain unchanged. The reviewed component correction is now distributed in
v3.0.3; historical assets are not rewritten. No live Immich connection or installed
desktop smoke test was performed. WinGet external acceptance and Flathub onboarding
are separate from successful GitHub/Pages publication.

Final evidence is saved locally after the immutable release tag; it does not
change the published source or artifacts. `M-RELEASE-303-20261111` is complete.
Remote main and v3.0.3 remain at `e0d1c40`. No release validation work remains;
external WinGet acceptance and optional Flathub onboarding are separate follow-up
items.
