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
source inspection alone does not establish the deployed updater revision.

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
- No old updater rerun was used to claim validation of the new rule. Once merge
  is active, verify fresh default-branch general NuGet and Avalonia refresh
  runs, their effective ignore input and absence of `illformed_requirement`.
  Do not merge #32 or enable auto-merge.
