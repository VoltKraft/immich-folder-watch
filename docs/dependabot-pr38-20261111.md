# Dependabot PR #38: actions/checkout v7.0.1

Reviewed on 2026-11-11 against main `a82216d4251e6517b71236602ab09abfdb13f3e1`.
The existing Dependabot branch was refreshed with a normal merge; no merge into
main, automatic merge, release, or deployment is part of this preparation.

## Provenance and license

- The upstream `v7.0.1` tag resolves to `3d3c42e5aac5ba805825da76410c181273ba90b1` (the github-script tag is annotated and was dereferenced).
- The [exact source license](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/LICENSE) is MIT. These are build/workflow tools, not application binaries or bundled runtime dependencies; this update introduces no application-distribution license blocker for AGPL-3.0-only.
- [Upstream release notes](https://github.com/actions/checkout/releases/tag/v7.0.1) and the [exact action contract](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml) were reviewed.
- The action runs on Node.js 24. The repository uses GitHub-hosted runners; no self-hosted runner fleet needs migration. Existing Node.js 24 action use already requires runner 2.327.1 or newer. Remote execution is verified separately from this source review.

## Compatibility and trust boundaries

All existing checkout inputs and trusted refs are preserved. The new default refusal of privileged fork checkouts is kept enabled; no unsafe override was added. Existing credential persistence remains disabled. CI exercises checkout in Windows, Linux and both native Flatpak architectures.

Token scopes, checkout trust boundaries, event triggers, release inputs, artifact
retention, concurrency and publication policy remain unchanged.

## Validation

Local workflow security checks passed (6 passed; 4 PowerShell-only cases
deferred to Windows CI), all 5 release-manifest regression cases passed, and
`git diff --check` passed. Exact-head remote CI, CodeQL and
Dependabot status are recorded in the PR description and shared project status
after completion. Publication-only jobs are not triggered for validation.
