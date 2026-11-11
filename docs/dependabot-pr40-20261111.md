# Dependabot PR #40: actions/setup-dotnet v6.1.0

Reviewed on 2026-11-11 against main `a82216d4251e6517b71236602ab09abfdb13f3e1`.
The existing Dependabot branch was refreshed with a normal merge; no merge into
main, automatic merge, release, or deployment is part of this preparation.

## Provenance and license

- The upstream `v6.1.0` tag resolves to `0f4a354dd5547a28c70b7853dbd95d5b67886e73` (the github-script tag is annotated and was dereferenced).
- The [exact source license](https://github.com/actions/setup-dotnet/blob/0f4a354dd5547a28c70b7853dbd95d5b67886e73/LICENSE) is MIT. These are build/workflow tools, not application binaries or bundled runtime dependencies; this update introduces no application-distribution license blocker for AGPL-3.0-only.
- [Upstream release notes](https://github.com/actions/setup-dotnet/releases/tag/v6.1.0) and the [exact action contract](https://github.com/actions/setup-dotnet/blob/0f4a354dd5547a28c70b7853dbd95d5b67886e73/action.yml) were reviewed.
- The action runs on Node.js 24. The repository uses GitHub-hosted runners; no self-hosted runner fleet needs migration. Existing Node.js 24 action use already requires runner 2.327.1 or newer. Remote execution is verified separately from this source review.

## Compatibility and trust boundaries

Version 6 migrates action internals to ESM without changing existing inputs or outputs. The existing .NET 10.x and exact Flatpak SDK inputs remain intact, as does the conditional .NET 6 WinGet tooling input. Optional new inputs are not enabled. Windows/Linux CI and native Flatpak candidate builds exercise SDK setup; the conditional WinGet publication path is not executed.

Token scopes, checkout trust boundaries, event triggers, release inputs, artifact
retention, concurrency and publication policy remain unchanged.

## Validation

Local workflow security checks passed (6 passed; 4 PowerShell-only cases
deferred to Windows CI), all 5 release-manifest regression cases passed, and
`git diff --check` passed. Exact-head remote CI, CodeQL and
Dependabot status are recorded in the PR description and shared project status
after completion. Publication-only jobs are not triggered for validation.
