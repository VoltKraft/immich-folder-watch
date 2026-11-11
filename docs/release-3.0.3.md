# Release v3.0.3 verification

## Scope and preparation

The user explicitly authorized merging #32, verifying main and creating the new
release. #32 merged with an expected-head guard as
`3740ce067644d65a296c21fec0812b9c10c8d25f`, preserving reviewed head `ce0b711`.
Local maintenance/release evidence is integrated without rewriting history;
conflicts affected only brief/status summaries, and product files match the merge.

This compatible patch delivers the reduced Avalonia 12.1.6.1 component-license
remediation, D-Bus 0.94.1 alignment and SDK/offline provenance/CI fixes. No user
configuration or data migration is introduced. See the
[component audit](avalonia-component-audit-20261111.md),
[reduced-build contract](reduced-avalonia.md) and
[PR validation](dependabot-pr32-20261111.md).

Version preparation uses the repository bump script and AppStream generator:
3.0.3 product version, 3.0.3.0 assembly/file versions, dated 2026-11-11.
[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) and
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) were verified from
their official sources. Existing releases and signing identity remain immutable.

## Validation and publication

Local exact-version/date and preserved-changelog checks, AppStream validation,
five manifest tests and six workflow-security tests pass. Four PowerShell cases
are platform-skipped locally and covered by hosted Windows CI. Independent review
confirms the release diff changes only version/changelog/AppStream and documentation,
with no unintended product/workflow changes or additional reduced-build blocker.

Merge commit `3740ce0` is verified: [CI 43066118171](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43066118171)
passes all eight jobs, [CodeQL 43066119121](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43066119121)
passes all four analyses, and [NuGet 43066118345](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43066118345)
succeeds. Automatic release follow-up 43067269421 succeeds and skips publication
because v3.0.2 already exists. Release-commit CI/CodeQL, new native publication
and public asset verification remain pending. Do not interpret preparation as a published release. Require all four
Windows/Linux architecture assets and verify actual reduced Linux components and
signed Pages distribution. WinGet submission and Flathub preparation are distinct
from external acceptance. Automatic merging remains disabled; no live Immich
connection or application installation is part of this release verification.
