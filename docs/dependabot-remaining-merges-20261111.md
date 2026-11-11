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

These refreshed checks and the final hosted main evidence remain pending at
this checkpoint.
