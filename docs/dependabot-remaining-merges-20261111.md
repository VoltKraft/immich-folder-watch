# Reviewed dependency merges — 2026-11-11

## Authorization and preflight

The user explicitly selected merging the seven prepared PRs and checking main.
The previous [preparation report](dependabot-remaining-prs-20261111.md) remains
historical evidence. Fresh preflight confirmed each original prepared head was
OPEN/CLEAN with all current checks successful, auto-merge disabled, and #32
unchanged/open at `51898a8d128327a1f58d8f392c898d18c7b9923a`.

Merges use GitHub's normal merge method and expected-head SHA guard. No branch
protection/check bypass, automatic merge, version bump, manual release or
publication of accumulated local documentation is selected.

## Executed merges

| PR | Verified head | Merge commit |
| --- | --- | --- |
| #38 | `a1ebfc78bf7584c32fda6d5a0bd7e4912abfff52` | `02666be3803f03d564e2887d1c9041438d4d359a` |
| #40 | `a758f1422e84c4a517504a768e74a8b7cdb7fd32` | `294300144d485c329bbe520b934bf5ad744f8c24` |
| #39 | `395225d662b52dbd1214c53d029be23476a65614` | `de55f2dabd48a0d5f7a9fbea4dec7f54b87ba1df` |
| #43 | `564269d33adffbbf7984f00d23eb54bd5e734a38` | `6a99ed310a3257695c65a8634be291e77ebb2fe3` |
| #42 | `d1ebef8940e2bf35f678b8684ac89c61513983e2` | `f00eb5a12ed5848cf180ba8ff6d18f2a496cd4b1` |
| #44 | `17bfa335bd61e7894d0a490a39f19b0637df446b` | `9a353d3e2e18a89cd62a21523e23b165b9033e42` |
| #45 | `68ce4fedb731b30da7be3fb2beff4afa274eeb34` | `efeda2ffb6ec975188d2b1454c39dd718c00e540` |

## Conflict resolution and combined validation

Subsequent merges exposed additive conflicts in the changelog and license
catalog/provenance files. #42 and #44 are refreshed with ordinary main merges;
#45 also includes their exact refreshed heads so its final checks exercise the
entire selected dependency set before the final main merge. Both sides of each
changelog/README addition and all exact-version license/source mappings survive.
JSON merges reject differing edits to the same value instead of choosing a side.

The combined inventory verifies 24 exact source SHA-256 checksums and 109 package
version mappings. All 15 notice-helper regression tests pass. A Git attribute
recognizes the original upstream trailing space in the versioned SVG license;
its checksum and bytes remain unchanged. No production logic changes beyond the
already reviewed PRs are introduced by these conflict resolutions.

The combined portable Core suite passes all 501 tests. Independent read-only
review at `190f86edf9fb27bdd4b6b808933524387407fca8` finds no actionable issue:
all 16 changed source/workflow/project files match the exact union of previously
reviewed edits. Product version, SDK, Avalonia project, Dependabot configuration
and strict notice installer remain unchanged. The review independently verifies
the complete license/source inventory and additive documentation resolutions.

| Refreshed PR | Exact integration head | CI / CodeQL / NuGet runs |
| --- | --- | --- |
| #42 | `d1ebef8940e2bf35f678b8684ac89c61513983e2` | 43018953526 / 43018945424 / 43018942779 |
| #44 | `17bfa335bd61e7894d0a490a39f19b0637df446b` | 43018930238 / 43018923364 / 43018919857 |
| #45 | `190f86edf9fb27bdd4b6b808933524387407fca8` | 43019305657 / 43019297562 / 43019295715 |

All three refreshed heads passed all 14 checks. #42 and #44 then merged.
GitHub still reported #45 DIRTY against the older 6a99ed3 base despite actual
main being 9a353d3. Automatic approval review rejected merging while that service
state was conflicting. Local `git merge-tree` against actual main succeeded and
produced exactly the already reviewed tree
`edb08a47b902211878b3625c6935d60957481d57`.

To resolve the inconsistent mergeability state safely, a normal main merge
creates #45 head `68ce4fedb731b30da7be3fb2beff4afa274eeb34`. Its entire tree is
identical to 190f86e (`git diff --exit-code` passes); no code, configuration or
license change is introduced. This head receives a fresh hosted check cycle
before another expected-head merge attempt. No rejection or check is bypassed.
GitHub now confirms MERGEABLE against current main 9a353d3. The fresh runs are
CI 43020656839, CodeQL 43020650278 and NuGet 43020648053. Final hosted main evidence
remains pending. Existing release v3.0.1 still points to 1ab0748 with four published
assets; no version or publication change was made.

## Final main verification

The final #45 head passed all 14 checks and GitHub confirmed MERGEABLE/CLEAN;
the expected-head merge then succeeded as `efeda2f`. Its tree exactly equals
the reviewed and tested integration tree `edb08a47b902211878b3625c6935d60957481d57`.
All seven authorized PRs have merged. Final main validation succeeds:

- [CI 43021602143](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43021602143): all eight jobs pass, including Windows/Linux tests, both native Flatpak architectures and Pages artifact validation.
- [CodeQL 43021602894](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43021602894): all four language analyses pass.
- [NuGet 43021602079](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43021602079): automatic dependency submission succeeds.
- All 13 main validation checks succeed. Open code-scanning and Dependabot alert queries both return zero after analysis.

[Release follow-up 43022515575](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43022515575)
succeeds. Its prepare job checks out the exact final main commit, detects that
`v3.0.1` already exists and explicitly skips artifact builds/publication. Windows
and Flatpak release builds, GitHub publication, Flathub, Flatpak repository and
WinGet update jobs are skipped. The release remains published with four assets,
original timestamp 2026-11-10T23:43:06Z and unchanged tag commit
`1ab074841c76b2493dc3af5d972ce229e5746edb`.

Final GitHub reads confirm all seven selected PRs MERGED with the recorded
commits. Only #32 remains OPEN at unchanged `51898a8`; its license block remains.
Repository `allow_auto_merge` is false and #32 has no auto-merge request.
No live Immich access or additional publication was performed.

Local main incorporates remote main through merge `abe5ad4`, retaining all prior
unpublished documentation. Every local changelog line was mechanically verified
as present in the remote complete changelog before resolving that local conflict.
Only documentation differs from remote main; production files match exactly.

## Documentation publication follow-up

The user subsequently authorized publishing this final report and the related
local maintenance evidence on main. The net publication diff changes only nine
documentation files; it introduces no additional product or workflow change.
The existing CI workflow supports manual dispatch and skips documentation-only
pushes, so an explicit CI run will verify the published revision.

A new release is recommended as v3.0.2: the YAML writer correction fixes existing
string-value loss, while the reviewed dependency/build changes preserve the
application's compatibility contract. Under the repository's
[Semantic Versioning policy](https://semver.org/spec/v2.0.0.html), these changes
fit a patch release. This is an assessment, not release authorization; version,
release tag and published artifacts remain unchanged.
