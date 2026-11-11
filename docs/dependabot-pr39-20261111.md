# Dependabot PR #39: actions/github-script v9.0.0

Reviewed on 2026-11-11 against main `a82216d4251e6517b71236602ab09abfdb13f3e1`.
The existing Dependabot branch was refreshed with a normal merge; no merge into
main, automatic merge, release, or deployment is part of this preparation.

## Provenance and license

- The upstream `v9.0.0` tag resolves to `3a2844b7e9c422d3c10d287c895573f7108da1b3` (the github-script tag is annotated and was dereferenced).
- The [exact source license](https://github.com/actions/github-script/blob/3a2844b7e9c422d3c10d287c895573f7108da1b3/LICENSE.md) is MIT. These are build/workflow tools, not application binaries or bundled runtime dependencies; this update introduces no application-distribution license blocker for AGPL-3.0-only.
- [Upstream release notes](https://github.com/actions/github-script/releases/tag/v9.0.0) and the [exact action contract](https://github.com/actions/github-script/blob/3a2844b7e9c422d3c10d287c895573f7108da1b3/action.yml) were reviewed.
- The action runs on Node.js 24. The repository uses GitHub-hosted runners; no self-hosted runner fleet needs migration. Existing Node.js 24 action use already requires runner 2.327.1 or newer. Remote execution is verified separately from this source review.

## Compatibility and trust boundaries

The release scripts use the injected github.rest client and CommonJS helpers. They neither require the now ESM-only @actions/github package nor redeclare the newly injected getOctokit parameter. CI now executes the exact action with contents: read, loads the real Flathub CommonJS helper, performs a read-only repository lookup, and checks core.setOutput. Publishing, dispatching and pull-request creation are not exercised by this smoke test.

Token scopes, checkout trust boundaries, event triggers, release inputs, artifact
retention, concurrency and publication policy remain unchanged.

## Validation

Local workflow security checks passed (6 passed; 4 PowerShell-only cases
deferred to Windows CI), all 5 release-manifest regression cases passed, and
`git diff --check` passed. All 9 GitHub Script bodies compile with the v9 injected
parameters, and the existing Flathub helper tests passed under Node.js. Exact-head remote CI, CodeQL and
Dependabot status are recorded in the PR description and shared project status
after completion. Publication-only jobs are not triggered for validation.

The first refreshed head `263b1ab` passed all 14 CI/CodeQL/dependency-submission
checks, including the actual v9 smoke test. The independent Dependabot app check
`130500249152` remained queued with no output; its authenticated checks page
provided no restart control. This final changelog checkpoint requests fresh
checks naturally without modifying the validated Dependabot configuration or
bypassing the outstanding service result.
