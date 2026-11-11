# Dependabot xUnit ignore correction (2026-11-11)

## Failure and selected fix

Automatic NuGet update runs [43003931719](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43003931719)
and [43003935654](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43003935654)
failed with `illformed_requirement`, message `[4.0.0,)`. Both job inputs identify
this as the existing xunit.v3 ignore condition in `.github/dependabot.yml`.

[PR #41](https://github.com/VoltKraft/immich-folder-watch/pull/41), head
`ed1a5f624970fd1e046a0584fc363d47c5372925`, replaces the interval spelling with
`>= 4.0.0`. It preserves the absolute version boundary for version and security
updates, including the xUnit 4 incompatibility with the current Avalonia bridge.
No package version, automatic merge setting or other update option changes.

The [C# requirement parser](https://github.com/dependabot/dependabot-core/blob/bbaa42a223acbd059d11a3475ae0c5aded0ec1a3/nuget/helpers/lib/NuGetUpdater/NuGetUpdater.Core/Analyze/Requirement.cs)
accepts comparison operators and splits comma-separated requirements before
version parsing; this explains rejection of the bracketed interval. Independent
review found no defect in the replacement. Explicit ignored versions remain active
for security updates in [IgnoreCondition](https://github.com/dependabot/dependabot-core/blob/bbaa42a223acbd059d11a3475ae0c5aded0ec1a3/common/lib/dependabot/config/ignore_condition.rb).
Ruby-side range normalization differs; inability to run local Ruby is not the
central validation gap. Exact hosted updater execution remains necessary because
source inspection alone does not establish the deployed updater revision. The
subsequent hosted execution below confirms the effective rule and parser recovery.

## Validation and activation boundary

- YAML parsing and exact before/after semantic comparison passed: only the xUnit
  ignore expression changes. Focused diff/whitespace review passed.
- PR [CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43008199290)
  and [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43008194872):
  all eight CI jobs, all four analyses, aggregate CodeQL and NuGet submission
  passed (14 successful checks), with clean mergeability.
- Executed unmodified upstream Requirement.cs at the source commit linked above,
  SHA-256 `8e8057f6db9c0572103a26ed67f1b06806eb8d97e7f3a22ae60067eb78ee837b`,
  using SDK 10.0.203 and existing NuGet.Versioning 7.3.1.0. Old interval throws
  ArgumentException; comparator parses. Versions 3.2.2/3.9.99 are not ignored,
  4.0.0/4.1.0/5.0.0 are ignored; zero failures and exit code 0. Scratch evidence:
  `/tmp/ifw-requirement-validation/`; no package downloads or repository vendoring.
- Automatic approval review rejected direct publication to main, requiring a PR
  or explicit push approval. The rejected command did not run. The fix is safely
  published on a new branch. The user subsequently explicitly authorized merge
  and verification; #41 merged as `a82216d4251e6517b71236602ab09abfdb13f3e1`.
  #32 remains excluded from this authorization.
- No old updater rerun was used to claim validation of the new rule. The fresh
  default-branch run below verifies the effective ignore input and parser recovery.
  #32 was not merged and auto-merge was not enabled.

## Default-branch verification

- Merge commit: `a82216d4251e6517b71236602ab09abfdb13f3e1`.
- [Main CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43009216820): all eight jobs succeeded.
- [Main CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43009217398): all four analyses succeeded.
- [NuGet submission](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43009216792): succeeded.
- Dependabot configuration check `130484289209`: succeeded.
- [Release follow-up](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43010112919):
  preparation succeeded; all builds/publication/downstream jobs skipped because
  v3.0.1 already exists. No new release or deployment.

The authenticated Dependabot UI showed automatic version job `1695671454` and
rebase job `1695674450` ending with an unknown error, without available logs or
corresponding Actions runs. This does not establish another requirement-parser
failure. A single controlled UI **Check for updates** started job `1695683622`,
[Actions run 43009535605](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43009535605).
The run completed successfully after 17m 35s. Full log evidence (97,269 lines)
contains `"version-requirement": ">= 4.0.0"`, zero occurrences of
`illformed_requirement`, and normal updater completion. xunit.v3 remained 3.2.2;
analysis found no updatable version under the ignore rule. This confirms the
specific requirement-parser fix in the real hosted updater, beyond YAML checking.

Created four review-only PRs: [#42](https://github.com/VoltKraft/immich-folder-watch/pull/42)
Microsoft.Extensions, [#43](https://github.com/VoltKraft/immich-folder-watch/pull/43)
SocketIOClient, [#44](https://github.com/VoltKraft/immich-folder-watch/pull/44)
Svg.Skia, and [#45](https://github.com/VoltKraft/immich-folder-watch/pull/45)
YamlDotNet. Their compatibility, licenses and CI are outside this assignment;
none was merged or approved for merging.

## Remaining independent warnings

Actions reports the new updater run as successful. The Dependabot job UI still
labels that job with `Dependabot failed to create a pull request` and another
error, and its detail view reports `PR for branch already exists`. The Actions
log recognizes the existing Avalonia 12.1.6 PR and continues; it contains no
requirement error. The exact duplicate-create operations are not identified in
that output, so do not claim every Dependabot internal operation is clean.
The initial automatic version/rebase jobs above also retain their unknown-error
states without logs; a successful separate #32 rebase is not claimed.

These remaining service/PR-handling warnings were not bypassed by closing,
recreating or merging #32. Any later remediation must preserve its license block.
The requested xUnit correction and hosted verification are complete with these
independent warnings explicitly retained.

Final readback: main remains `a82216d`; #41 closed/merged; #32 open at unchanged
`51898a8d128327a1f58d8f392c898d18c7b9923a`, auto-merge request null, repository
`allow_auto_merge=false`, zero open code-scanning alerts. v3.0.1 is unchanged.

Evidence retained outside Git:
- `/tmp/ifw-nuget-ignore-fixed-complete.log` (full hosted log).
- `/tmp/ifw-dependabot-nuget-success-20261111.jpg` (UI completion screenshot).
- `/tmp/ifw-requirement-validation/` (isolated actual-parser reproduction).

The final documentation is committed locally; no additional main push or release.
