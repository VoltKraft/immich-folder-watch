# Dependabot configuration-check diagnosis (2026-11-10)

The user subsequently deferred this recovery and left #34 open. No further
retry or support contact is selected; the following records the investigation.

## Finding

PR #34 has a stalled GitHub Dependabot App configuration-validation job, separate
from GitHub Actions CI and CodeQL. No repository configuration defect was found.
The available evidence points to service-side dispatch/processing, but GitHub's
internal job logs are unavailable and the underlying implementation fault is
not established. Recovery has not been verified.

## Evidence

- Original PR head: `f4412966f9e3008fb286945abcaa65a417e83996`.
- Original CheckRun: `130138962423`; CheckSuite: `116196471583`.
- Owner: GitHub Dependabot App, ID 29110. Check name: `.github/dependabot.yml`.
- Created/started: 2026-11-10 21:23:15 UTC. Suite update time never advanced;
  status remained `queued`, with no conclusion, completion, output or annotations.
- Config blob `8a884bd4cfbc4213e44cfdd7ef80009c690b6e58` is byte-identical on
  main and #28/#31. Those PR checks completed successfully within one second,
  reporting `Dependabot config file validation` / `All changes look good`.
- The exact config also passed the retained Dependabot JSON Schema locally.
  All normal application/platform CI and CodeQL checks on the old head passed.
- GitHub's public status API reported no active incident at inspection; this
  does not exclude a narrower Dependabot service fault.

## Recovery attempts

1. The documented [CheckSuite rerequest REST endpoint](https://docs.github.com/en/rest/checks/suites#rerequest-a-check-suite)
   returned HTTP 404 with the authenticated user token. No retry was accepted.
2. GitHub schema introspection exposed `rerequestCheckSuite`; the corresponding
   GraphQL mutation returned `FORBIDDEN` and explicitly required a GitHub App.
   This is an API capability limit, not a local approval-review rejection.
3. The user signed into the browser. The actual Dependabot check detail view
   exposed no rerun control; the rerun controls visible for Actions jobs do not
   target this app-owned check. No unrelated job was restarted via the UI.
4. A controlled retrigger was pushed as `f22797ed4d452e1940493bf09d44b25b931b2ee8`
   to the existing PR branch. It adds one explanatory YAML comment about
   repository-level auto-merge settings. Parsed configuration before/after is
   equal, schema validation passes, and the reviewed SkiaSharp proposal is intact.
   No force-push, setting change, code change or merge was used.
5. The push created new CheckRun `130148023423`, CheckSuite `116203491343`, at
   2026-11-10 21:39:28 UTC. It also remained queued without diagnostic output.
   The retrigger therefore did not demonstrate recovery of the service.

The [upstream configuration-validation discussion](https://github.com/dependabot/dependabot-core/issues/4605)
contains a maintainer's description of historical GitHub-internal PR validation
problems. It supports the plausibility of a service issue; it does not prove that
this run has the same cause. No arbitrary config change or check bypass is justified.

## Handoff for GitHub support

Repository: `VoltKraft/immich-folder-watch`; PR: [#34](https://github.com/VoltKraft/immich-folder-watch/pull/34).
Supply the two CheckRun/CheckSuite IDs, timestamps and heads above. Request
inspection/requeue of the Dependabot-owned configuration validator and its event
processing. The same config passes on #28/#31; a comment-only push reproduces the
queued state. No support request has been sent.

Current-head [CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42907159639)
and [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42907153860)
both completed successfully on `f22797e`: six CI jobs, four language analyses and
the aggregate CodeQL check pass. NuGet submission also passes. The configuration
check is the sole unfinished check (12 successes, one queued). Full handoff state
is tracked in [project status](status.md).
PR #32 remains open/blocked at `51898a8`; auto-merge stays disabled. No PR was merged,
no release/deployment occurred, and no check result or protection was overridden.
