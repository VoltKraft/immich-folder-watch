# Project Status

## Remaining PR fixes prepared; final verification in progress (2026-11-11)

- #38, #40, #42 and #44 are pushed and pass their exact-head CI and all four
  CodeQL analyses. Both native Flatpak architectures succeed; #38/#40 also
  pass their separate Dependabot configuration checks.
- #39 passes CI/CodeQL, including a new read-only v9 runtime smoke test. Its
  first Dependabot app check stayed queued without output or a restart control.
  The final changelog checkpoint `395225d` starts a fresh ordinary check cycle.
- #45 `9fe9d27` restores both exact-source MIT notices and fixes a discovered
  YAML string round-trip defect reproduced on both old and new versions.
  All 498 portable Core tests, 15 license tests and all 14 hosted checks pass.
- #39 final head `395225d` now also passes all 14 checks; its old queued app
  check belongs to the previous head and is not claimed successful.
- Independent security review of #43 identified and verified the fix for a
  stop/reconnect lifetime gap in SocketIO 4. Head `63f1f9a` passes Windows/Linux
  and CodeQL but native Flatpak exposes missing 10.0.3 notices in the broader
  offline feed. Final repair `564269d` adds only those five exact-source MIT
  versions; all 89 CI-feed archives pass checksum and notice installation.
  Final hosted CI/CodeQL runs are active.
- #32 remains open at unchanged `51898a8`; all PR auto-merge requests remain
  null. No merge, main push, release, deployment or live Immich test performed.

## Remaining PR preparation selected (2026-11-11)

- Selected `M-REMAINING-PRS-20261111`: #38/#39/#40/#42/#43/#44/#45, excluding #32.
  Current remote main is `a82216d`; local unpublished evidence is preserved.
- Separate worktrees isolate Actions, SocketIO, branding, Hosting and YAML work.
  Root brief/status and final cross-cutting evidence remain primary-owned.
- Initial evidence: #42 application/Flatpak CI succeeds but CodeQL is neutral;
  #44/#45 fail native Flatpak packaging; #43 has major transport API changes.
  Exact-source license reviews and fixes are in progress. No merge is selected.

## Dependabot xUnit correction verified; separate warnings retained (2026-11-11)

- Completed scoped correction/verification `M-DEPENDABOT-IGNORE-20261111`. Replaced the interval with
  `>= 4.0.0` on isolated branch `fix/dependabot-xunit-ignore`; scope retains
  absolute version/security exclusion and changes no package versions.
- [PR #41](https://github.com/VoltKraft/immich-folder-watch/pull/41) head
  `ed1a5f624970fd1e046a0584fc363d47c5372925` contains the fix and focused docs.
  YAML semantic comparison and all 14 PR CI/CodeQL checks passed. The actual
  upstream C# parser reproduced the old failure and passed all five version
  boundary cases for the correction.
- Automatic approval review rejected the direct main push and required a PR or
  explicit publication approval. The user then explicitly authorized merging #41;
  expected-head merge succeeded as `a82216d4251e6517b71236602ab09abfdb13f3e1`.
  Main CI, CodeQL, dependency submission and config validation passed; automatic
  release follow-up correctly skipped publication. #32 stays blocked; auto-merge off.
- Independent source review confirms the C# updater parser supports the comparator
  and retains explicit ignore versions for security updates. A controlled fresh
  NuGet run `43009535605` succeeded with the new effective rule, zero requirement
  errors and xunit.v3 still 3.2.2. Created #42-#45 for review only.
- Dependabot UI retains separate duplicate-PR creation warnings and initial
  automatic version/rebase unknown errors. No successful #32 rebase is claimed.
  Next maintenance action: investigate those service/PR-handling warnings while
  retaining #32's license block. [Detailed evidence](dependabot-ignore-20261111.md).
- Final evidence is saved locally; no additional main documentation push.

## PR #34 merged; main verified, separate updater issue found (2026-11-11)

- User authorized the merge and main verification. Rechecked all 14 successful
  PR-head checks and merged exact head `1a4722c` as
  `eeba23df3a62a6cf307684b3a1a6f4d607d7118b`, without bypass or auto-merge.
- Main CI `43003920977` passed all eight jobs; CodeQL `43003920330` passed
  all four analyses; NuGet submission `43003920444` succeeded. Open code-scanning
  alerts: zero. Dependabot configuration check `130466569912` also succeeded.
- Release follow-up `43004699915` succeeded and correctly skipped publication
  because v3.0.1 exists. No new release, Pages deployment or downstream submission.
- Separate automatic NuGet updater runs failed with `illformed_requirement` for
  the existing xunit.v3 ignore range `[4.0.0,)`. Merge/verification completed;
  updater maintenance remains open. [Detailed evidence](dependabot-pr34-20261111.md).
- Local documentation conflicts preserve the newer validation/release records;
  implementation changes match remote main. No extra main push is selected.
- #32 remains open/blocked at unchanged `51898a8`; #34 is closed/merged and
  auto-merge disabled. Next maintenance action: validate/correct the xUnit ignore
  requirement and rerun NuGet updater jobs while preserving compatibility blocks.
  No configuration fix or additional remote push was performed in this assignment.

## PR #34 ready for a separate merge decision (2026-11-11)

- Completed `M-PR34-20261111`; refreshed #34 from `f22797e` onto remote main
  `2a9a96d` and pushed `1a4722c` without force-push or merging.
- Branding builds, pixel/ICO comparison and runtime-isolation verification pass;
  renewed license review found no blocker. All eight CI jobs, all four CodeQL
  analyses, aggregate CodeQL and NuGet submission succeeded: 14 successful checks.
- GitHub reports `MERGEABLE` / `CLEAN`; zero open code-scanning alerts. PR body
  contains exact-head evidence. Next action requires a separate user merge decision.
- No Dependabot configuration suite has appeared on the new head; the old queued
  checks remain historical, not successfully rerun. See [renewed evidence](dependabot-pr34-20261111.md).
- #32 remains blocked, auto-merge disabled, remote main and release v3.0.1 unchanged.
  Final evidence is saved locally; only the #34 branch and its description were
  updated remotely. No main documentation push.

## PR #37 merged and main verified (2026-11-11)

- User authorized merging #37 and verifying main. All 14 PR-head checks passed
  at `d79d3f3`; expected-head merge succeeded as
  `2a9a96d18ead49682804cdbe61e444b8c5f99703`, without bypassing checks.
- [Main CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43000078507)
  passed all eight jobs, including Windows/Linux tests, both native Flatpak
  candidates and both actual Pages upload/download modes.
  [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43000084573)
  passed all four analyses; NuGet submission succeeded. Open code-scanning
  alert count remains zero.
- [Release follow-up](https://github.com/VoltKraft/immich-folder-watch/actions/runs/43000811523)
  succeeded in preparation and correctly skipped builds/publication because the
  v3.0.1 tag already exists. No release, Pages deployment or downstream submission
  was performed by this merge; published v3.0.1 remains unchanged.
- Final readback: #37 merged/closed; #32/#34 open/unmerged with no auto-merge
  requests, repository auto-merge disabled. Requested merge/validation completed.
- Local main includes the merge and preserves local v3.0.1/PR verification records.
  Documentation-only conflicts were reconciled without implementation changes.
  Final evidence is committed locally; no additional main documentation push.


## PR #37 ready for a separate merge decision (2026-11-11)

- `M-PR37-20261111` completed. Updated [PR #37](https://github.com/VoltKraft/immich-folder-watch/pull/37)
  from `c8989d6` to `d79d3f30376f2993a185bfc62dd55e87865f943d`, integrating main
  `1ab0748` without force-push and adding focused Pages upload/download validation.
- All eight CI jobs, all four CodeQL analyses, aggregate CodeQL and NuGet submission
  passed: 14 successful checks. Actual upload/download passed with both hidden-file
  modes; no deployment rights, environment or signing secrets were used.
- License/compatibility review and independent review found no blocker. GitHub
  reports the PR clean and mergeable. Its description contains exact-head run links.
- #37 remains open/unmerged; #32/#34 are unchanged/open, repository auto-merge off.
  Main/release v3.0.1 are unchanged. A merge requires a later user decision.
- [Detailed PR evidence](dependabot-pr37-20261111.md) records action source/license
  links, test coverage, uploaded fixture IDs and remaining deployment limitation.
  Final evidence is a local documentation checkpoint; only PR #37 was pushed.


## v3.0.1 published and verified (2026-11-11)

- `M-RELEASE-301-20261111` completed. [v3.0.1](https://github.com/VoltKraft/immich-folder-watch/releases/tag/v3.0.1)
  is the latest stable release, tagged at `1ab074841c76b2493dc3af5d972ce229e5746edb`.
  The release includes all previously merged main changes and the verified
  container-ownership fix discovered during release validation.
- R301-AC01/02: Unified versions/AppStream/changelog match; six CI jobs and all
  four CodeQL analyses passed; both Windows MSIs and both Linux Flatpaks built,
  published and independently downloaded with matching size/SHA-256.
- R301-AC03: Signed Pages repository deployed; live signature/version verification
  passed for both architectures. WinGet submission succeeded (external PR open).
  Flathub preparation/builds passed; disabled submission was correctly skipped.
- R301-AC04: #32/#34 remain open/unmerged, auto-merge disabled, no live Immich or
  personal installation changes. No further milestone is selected.
- [Detailed evidence](release-3.0.1.md) owns run links, checksums, signed refs and
  publication limits. This final documentation checkpoint follows the immutable
  release and is retained locally; published artifacts remain unchanged.


## PR #37 preparation (2026-11-11)

- User selected `M-PR37-20261111`, authorizing branch refresh, focused compatibility
  validation and successful CI/CodeQL without merging or deployment.
- Integrated remote main `1ab0748` into original PR head `c8989d6` in an isolated
  worktree. No force-push; the root checkout's local v3.0.1 evidence is preserved.
- Add an actual upload/download smoke check for the Pages action using synthetic
  files only, read-only repository permissions and no publishing job/secrets.
- #32/#34 and disabled automatic merging are outside the mutation scope.


## v3.0.1 container checkout correction (2026-11-11)

- Preparation commit `b475dda` passed all six [CI jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42922983220)
  and all four [CodeQL analyses](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42922982812).
- The first [release build](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42923750608)
  failed before either Flatpak build: Git rejected the guard's `rev-parse` with
  `dubious ownership`. Checkout's temporary HOME does not carry its safe-directory
  configuration into subsequent shell steps in the privileged build container.
  This was an ownership-check failure, not a different target SHA.
- Scope the guard's Git trust exception to `GITHUB_WORKSPACE` for that single
  command. Keep strict target equality and default-branch checkout; do not add a
  global/wildcard exception. Extend the deployed-guard regression with Git's
  different-owner simulation, checking that plain Git rejects the fixture while
  the scoped guard accepts only its exact HEAD and rejects all other inputs.
- No v3.0.1 tag or assets were published by the failed run. Rerun full exact-head
  CI and release builds after this focused correction; prior versions stay intact.


## v3.0.1 release preparation (2026-11-11)

- User authorized publishing v3.0.1 from current main `bb13a33`, including all
  merged maintenance/security changes; selected `M-RELEASE-301-20261111`.
- Remote v3.0.1 release/tag are unused. Local main matches origin/main and the
  working tree was clean before preparation. Existing v3.0.0 assets are preserved.
- Unified versions are prepared as 3.0.1 / 3.0.1.0; release notes retain every
  Unreleased item and summarize the merged dependencies/actions and maintenance
  records. Release date uses the user's Europe/Berlin date, 2026-11-11.
- Publication follows successful main CI through the existing release workflow;
  verify all four assets and downstream signed Flatpak repository before handoff.
  No publication/build success is claimed at this preparation checkpoint.
- Local preflight passed: version/XML/changelog consistency, AppStream validation,
  five manifest regressions and five workflow-security tests (four PowerShell
  cases require Windows CI), plus whitespace checks. Independent release review
  found no blocker in the five-file preparation diff.
- #32 and #34 remain excluded from main; auto-merge stays disabled.


## Release checkout fix verified on main (2026-11-10)

- Published security fix `ae9558c` and Windows regression-runner correction
  `f1d20c3f1f802d67194d8ae620acc792c796ab7c`; remote main is the latter revision.
- [CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42916629585)
  completed successfully on `f1d20c3`: all six jobs passed, including Windows/Linux
  builds/tests, all nine workflow security cases on Windows, and native x86_64/ARM64
  Flatpak candidates. Selecting Git Bash resolved the initial Windows test failure.
- [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42916628594)
  completed successfully on the same revision for all four languages. NuGet
  dependency submission also passed. The open code-scanning alert list is empty.
- Alerts [#11](https://github.com/VoltKraft/immich-folder-watch/security/code-scanning/11)
  and [#12](https://github.com/VoltKraft/immich-folder-watch/security/code-scanning/12)
  are both `fixed`, automatically recorded at 22:38:28 UTC; neither was dismissed.
- Final remote readback: #32 and #34 remain open/unmerged, both have no auto-merge
  request, and repository automatic merging remains disabled.
- Requested publication and validation are complete. This final evidence-only
  status entry is a local documentation checkpoint after the verified remote
  revision; no further implementation work or release dispatch is selected.


## Release checkout fix published; Windows test runner correction (2026-11-10)

- User explicitly authorized publishing the fix and verifying CI, CodeQL and
  alert closure. Pushed `ae9558ce07b93183c11c878d96aab0940488c37d` to main.
- CodeQL automatically marked alerts #11 and #12 `fixed` at 22:38:28 UTC;
  no dismissal was performed. The Actions analysis passed on the pushed fix.
- Initial [CI run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42916337435)
  exposed a Windows-only test harness problem: the new Bash regression's valid
  commit case failed before application build; all four PowerShell cases passed.
  Select Git for Windows' Bash explicitly instead of the ambiguous PATH launcher,
  and include stdout in assertion diagnostics. Release behavior and assertions
  remain unchanged. Fresh exact-head CI is required for this correction.
- #32/#34 remain open at their original heads, with `auto_merge: null`;
  repository `allow_auto_merge` is false. No PR merge or release dispatch.


## Release checkout alerts hardened locally (2026-11-10)

- Live CodeQL alerts [#11](https://github.com/VoltKraft/immich-folder-watch/security/code-scanning/11)
  and [#12](https://github.com/VoltKraft/immich-folder-watch/security/code-scanning/12)
  remain open on remote main `85ec9e4c45547fd353c647bf2c641550178e172f`.
  Both report `actions/cache-poisoning/poisonable-step` after the same dynamic
  Flatpak checkout, for `workflow_dispatch`.
- Existing gates already restrict dispatch to main and automatic runs to successful
  same-repository push CI on main. There is no dispatch SHA input, so no arbitrary
  external-commit exploit was demonstrated. The
  [CodeQL query guidance](https://codeql.github.com/codeql-query-help/actions/actions-cache-poisoning-poisonable-step/)
  explains why read-only repository permissions alone do not remove cache risk.
- Changed only the Flatpak release checkout to the explicit default branch, with
  an inline exact-commit guard before any repository script. The target remains
  manifest data. If main advances, the job stops instead of mixing SDK, manifest
  or offline-feed inputs from different commits. Retry behavior is documented in
  [publication workflow trust](development.md#publication-workflow-trust).
- Validation: five workflow security tests passed, including real Git-history
  matching/mismatched commits and malformed/injection inputs; four unrelated
  PowerShell cases were skipped because PowerShell is unavailable locally.
  Five manifest regression tests passed. YAML parsing/step-order checks and
  `git diff --check` passed. Independent security review found no blocking
  security or correctness issue; hosted CodeQL and Windows execution remain unverified.
- This is a local correction; no push, release dispatch, remote alert dismissal
  or hosted rescan was performed. Remote alert closure remains unverified until
  the fix is published and CodeQL scans it. #32/#34 and auto-merge are unchanged.
- The preceding documentation publication is complete: main `85ec9e4` passed
  [all six CI jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42911044302)
  after an explicit CI dispatch (documentation-only pushes are filtered), plus
  [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42910956556)
  and NuGet submission. A successful analysis job does not mean zero open alerts.


## Documentation publication checkpoint (2026-11-10)

- User authorized publishing the accumulated dependency-maintenance documentation
  to main and checking the resulting CI. Earlier statements below that records
  are local/unpushed describe their historical checkpoints, not a continuing
  publication restriction.
- Prepared from local checkpoint `2849aec` on remote baseline `9a84eec`; the
  accumulated diff changes only this status, the project brief, the Dependabot
  review and the configuration-check diagnosis. `git diff --check` passed.
- The preceding main revision passed CI and CodeQL as recorded below. Validation
  of the documentation push must be read from the checks attached to its exact
  GitHub commit; earlier runs do not establish the new revision's result.
- #32 remains open/blocked and #34 open/deferred. Automatic merging stays disabled.
  No additional dependency update, PR merge or version bump is selected.

## Remaining Actions PR merges completed (2026-11-10)

- User explicitly deferred #34 and authorized merging the other reviewed Actions
  updates (#28/#29/#30/#31). Each exact PR head had 13 successful checks before its
  manual merge. Expected-head checks protected against concurrent branch changes;
  no checks or branch rules were bypassed.

| PR | Validated head | Merge commit |
| --- | --- | --- |
| [#28](https://github.com/VoltKraft/immich-folder-watch/pull/28) | `c66de1e` | `b661638d9d7535a2a92c1cbfa510dc532d7dce05` |
| [#29](https://github.com/VoltKraft/immich-folder-watch/pull/29) | `2b2bdc6` | `b5f4dc122ed8203c9a17fae9f1330b1c057bc222` |
| [#30](https://github.com/VoltKraft/immich-folder-watch/pull/30) | `d0062e7` | `5c80ddd5a12c02b3badc549a1f72f4e33c8ec404` |
| [#31](https://github.com/VoltKraft/immich-folder-watch/pull/31) | `5ed2076` | `9a84eec0a5da6f9a5e58d92c0e776bc22f707309` |

- Final remote main: `9a84eec0a5da6f9a5e58d92c0e776bc22f707309`.
  [Combined main CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42909012903)
  and [CodeQL](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42909013941)
  completed successfully on that exact final merge commit. All six CI jobs passed,
  including Windows/Linux tests and native x86_64/ARM64 Flatpak builds; all four
  CodeQL language analyses passed. NuGet dependency submission also succeeded.
- #32 remains open/blocked at unchanged `51898a8`. #34 remains open/deferred at
  `f22797e`; no further configuration-check recovery was attempted after the user
  deferred it. Repository auto-merge remains disabled, with no PR auto-merge request.
- Local main incorporates the remote merges without losing local documentation
  history. No main documentation push, version bump, manual release or deployment.
- Completed: four authorized PR merges and successful combined main validation.
  No further milestone is selected; #32 remains blocked and #34 is explicitly
  deferred until a later user request. Final local evidence is not pushed.

## Dependabot configuration-check recovery blocked externally (2026-11-10)

- User authorized recovery of #34's queued Dependabot check without merges.
  Investigation and permitted recovery attempts are recorded in
  [the diagnosis and support handoff](dependabot-config-check-20261110.md).
- No config defect was identified: the original blob matches successful #28/#31
  validation, schema validation passes, and a comment-only retrigger preserves
  parsed YAML exactly. The evidence points to stalled GitHub Dependabot service
  processing; internal logs/root cause are unavailable and remediation is not claimed.
- REST retry returned 404; GraphQL explicitly restricts suite retries to GitHub
  Apps. After the user signed in, the actual Dependabot check UI still offered no
  rerun action. These are GitHub capability limits, not automatic approval rejection.
- Pushed only explanatory-comment commit `f22797ed4d452e1940493bf09d44b25b931b2ee8`
  to #34. New check `130148023423` remains queued, as does the superseded original
  `130138962423`; neither supplies diagnostic output. No further speculative
  commits, config changes, forged statuses or protection bypasses were performed.
- The new head has [all six CI jobs successful](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42907159639),
  including Windows/Linux and x86_64/ARM64 Flatpak, plus [all four CodeQL analyses](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42907153860),
  the aggregate CodeQL check and NuGet submission successful. Twelve checks pass;
  the separate configuration check is the sole unfinished check.
- PR #34 remains open/unmerged; #32 remains unchanged/open/blocked at `51898a8`,
  and repository auto-merge stays disabled. No main push, release or deployment.
- Remaining prerequisite: the owning GitHub service must process/requeue the
  validator. The linked handoff contains exact run/suite IDs, timestamps and
  reproduction evidence for GitHub support. No support request was sent. Local
  documentation is committed separately from the pushed PR comment.

## Remaining Dependabot refresh completed (2026-11-10)

- Milestone `M-DEPENDABOT-REFRESH-20261110` completed. User authorized updating
  #28/#29/#30/#31/#34 with current main and obtaining successful CI/CodeQL; no PR merges.
- GitHub update-branch requests used each exact expected head. All five new heads
  contain remote main `13e93dac570a49ec9e8595713c5fc9aeb2a78524`; ancestry and
  full diff checks confirm only each original reviewed proposal remains above main.
  No force-push, extra package change or test/check weakening was necessary.

| PR | Updated head | CI | CodeQL workflow |
| --- | --- | --- | --- |
| [#28](https://github.com/VoltKraft/immich-folder-watch/pull/28) | `c66de1e58f0bd4d31b5e004348909abcb8665f32` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904525439) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904516733) |
| [#29](https://github.com/VoltKraft/immich-folder-watch/pull/29) | `2b2bdc6c767e19beb0ebb58ae0ff32a7b8711110` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904530008) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904521815) |
| [#30](https://github.com/VoltKraft/immich-folder-watch/pull/30) | `d0062e7cccda5ec8ec19d55c58d7cf5b88074f5f` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904535257) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904528780) |
| [#31](https://github.com/VoltKraft/immich-folder-watch/pull/31) | `5ed20761e5ee96ba1fa9b16f90173273393da8c0` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904541922) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904531775) |
| [#34](https://github.com/VoltKraft/immich-folder-watch/pull/34) | `f4412966f9e3008fb286945abcaa65a417e83996` | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904546447) | [Success](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42904538706) |

- DCR-AC01/02: All six CI jobs passed on every updated head, covering Windows/Linux
  tests and native x86_64/ARM64 Flatpak builds. All four CodeQL analyses (Actions,
  C#, JavaScript/TypeScript, Python) and each aggregate `CodeQL` check passed.
  NuGet dependency submission passed too. The earlier neutral CodeQL assessment
  is resolved by the fresh analyses; no CodeQL configuration changes were needed.
- Separate service check: #34's `.github/dependabot.yml` check (ID 130138962423,
  [service details](https://dependabot-api.githubapp.com)) remains queued at this
  snapshot. It is not one of the completed CI/CodeQL jobs; no failure is reported.
  #28/#29/#30/#31 have all 13 reported checks successful; #34 has 12 successful
  and this one queued service check. Do not describe every #34 check as complete.
- DCR-AC03: All five PRs remain open/unmerged. #32 remains unchanged/open/blocked
  at `51898a8`; repository `allow_auto_merge: false`, all inspected PRs
  `auto_merge: null`. Remote main remains `13e93da`. No merge into main, main push,
  release, deployment or live Immich access occurred.
- Local records preserve authorization and validation; they are not pushed.
  No implementation milestone remains active. Next action: separately authorized
  review/merge after checking current heads and the outstanding service check.

The review below records the earlier heads; the refresh evidence above supersedes
its pending integration-CI and neutral-CodeQL limitations. Publication-only paths
remain outside the validation performed here.

## Remaining Dependabot review completed (2026-11-10)

- Reviewed #28/#29/#30/#31/#34 without remote changes. Exact heads, CI links,
  compatibility findings and upstream license sources are retained in
  [the review record](dependabot-review-20261110.md).
- All five exact-head CI runs completed successfully with six passing jobs each;
  NuGet dependency submission passed. CodeQL is neutral on every PR with
  `4 configurations not found`, so a successful security scan is not claimed.
- No concrete compatibility or license blocker was identified. Actions retain
  MIT licenses; #34 changes only the branding tool's SkiaSharp packages, preserving
  application runtime versions and native third-party notice coverage.
- All five heads integrate conflict-free with main `13e93da` in local tree-only
  checks. Their hosted CI predates the recent main merges. Before a later merge,
  refresh integration CI and obtain a complete CodeQL assessment. Pages/OIDC and
  release-only publication paths were not exercised or triggered by this review.
- All five PRs remain open/unmerged. #32 remains unchanged at `51898a8`, open and
  blocked; repository `allow_auto_merge: false`, with `auto_merge: null` on every
  inspected PR. No PR rebase, push, merge, workflow rerun or publication occurred.
- Review complete; no implementation milestone selected. Findings and scope are
  saved in a local documentation checkpoint only. A later merge needs separate
  authorization and current validation.

## Selective Dependabot merges completed (2026-11-10)

- User explicitly authorized merging #27, #33, #35 and #36 only. All four were
  merged manually with expected-head checks after every current-head check passed.
  Repository auto-merge remains disabled (`allow_auto_merge: false`); every
  inspected PR has `auto_merge: null`.
- Integration preserved every reviewed package version, deletion-race fix,
  regression test, xUnit compatibility constraint and license notice. Resolved
  overlapping status/changelog records and adjacent package declarations;
  removed duplicated historical status blocks without discarding history.
  Independent read-only review of final cumulative head `9f73d91` found no issues.

| PR | Validated head | Merge commit | Successful CI |
| --- | --- | --- | --- |
| [#27](https://github.com/VoltKraft/immich-folder-watch/pull/27) | `ca35782` | `20cf55a` | [All six jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42889338522) |
| [#33](https://github.com/VoltKraft/immich-folder-watch/pull/33) | `d5c5170` | `4f1ff08` | [All six jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42894339727) |
| [#35](https://github.com/VoltKraft/immich-folder-watch/pull/35) | `176796a` | `c705988` | [All six jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42894342541) |
| [#36](https://github.com/VoltKraft/immich-folder-watch/pull/36) | `9f73d91` | `13e93da` | [All six jobs](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42894348336) |

- Additional CodeQL and dependency-submission checks passed on all four heads.
  The cumulative CI covers Windows/Linux tests and native x86_64/ARM64 Flatpak
  builds. No guard, assertion or branch rule was bypassed.
- #32 remains open at unchanged head `51898a8`, blocked by the previously recorded
  technical and license issues. No Avalonia upgrade or reduced build was included.
- Follow-up live check: remote main remains `13e93da`. Its [post-merge CI](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42895589381)
  completed successfully (GitHub updated at 2026-11-10 20:35:07 UTC). All six jobs
  passed: Windows/Linux build and tests, packaging lint, candidate preparation,
  and native x86_64/ARM64 Flatpak builds. No version bump or manual release was performed.
- Follow-up settings readback: repository `allow_auto_merge: false`; #32 remains
  open/unmerged at unchanged `51898a8`, with `auto_merge: null` and unsuccessful
  checks (`mergeable_state: unstable`). Its technical/license blockers remain
  deferred. This inspection made no remote changes or workflow reruns.
- Local main incorporates the remote merges while preserving the earlier local
  documentation commits. This aggregate handoff remains local and is not pushed.
- Milestone `M-DEPENDABOT-CI-20261110` is complete for the selected four PRs, with
  #32 explicitly deferred. No further milestone is selected. Next action: a
  separately selected licensing resolution for #32 or review of other open PRs.

The following entries are historical snapshots; the merge record above supersedes
prior statements that the selected PRs were still open or awaiting authorization.

## Dependabot CI remediation (2026-11-10)

- Selected milestone: `M-DEPENDABOT-CI-20261110`. User authorized fixes on
  existing PR branches without merges; later explicitly deferred #32's Avalonia
  upgrade because of incompatible embedded component licensing.
- Isolated worktrees preserve each bot proposal and the original local main.
  Scoped corrections are pushed without force; no update PR is merged.

| PR | Cause and correction | Pushed correction | Validation |
| --- | --- | --- | --- |
| #27 | Concurrent watcher/poll deletion handlers read the same asset before tombstone persistence; per-path ownership and retained retry baseline prevent duplicate remote trash | `ca35782` (fix `05297b7`) | Two deterministic regressions fail against old source; 483 Core tests pass before review delta, five focused deletion cases pass after it; independent review passed; [all six CI jobs passed](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42889338522) |
| #33 | Missing reviewed supplemental notices for Microsoft.Extensions/System 11.0.0; verified exact source license and all package notices, added exact-version supplements | `c6ad2e9` | Both architecture restores and 87-archive combined feed verified; real notice installer and 15 guard regression tests pass; independent review passed; [all six CI jobs passed](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42888743407) |
| #35 | xUnit 4 changes parallelism API, test-runner defaults and Avalonia extension ABI; retain framework 3.2.2 and compatible v2/runner upgrades, exclude incompatible future v4 proposals | `a5cbed6` | 481 Core and 53 Linux GUI/protocol cases pass with no failures/skips; schema and independent review passed; [all six CI jobs passed](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42888754999) |
| #36 | Missing reviewed supplemental notices for Microsoft.Data.Sqlite/Core 11.0.0; verified MIT source and added exact-version supplements | `2b2b186` | Both architecture restores and 81-archive combined feed verified; real notice installer and 15 guard regression tests pass; independent review passed; [all six CI jobs passed](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42888749135) |

- No license guard or test assertion was disabled. SDKs: local application/tests
  10.0.203; exact Flatpak feed restores 10.0.401. PR corrections add no release bump.
- Completion: all six CI jobs pass on each of the four exact corrected heads,
  including Windows/Linux and native x86_64/aarch64 Flatpak builds. No unfinished
  or failed current-head check remains on #27/#33/#35/#36. All remain open with
  `auto_merge: null`; repository `allow_auto_merge: false` was read back again.
- Final #27 CI: Linux 483 Core + 53 GUI/protocol passed; Windows 474 Core + 36 WPF
  + 34 portable Linux-project tests passed, with 9/19 expected platform skips.
  Other corrected PRs: Linux 481 + 53; Windows 472 + 36 + 34 with the same skips.
  All application builds have zero warnings/errors. Both native license logs
  confirm 87 archives for #33 and 81 for #36.
- PR descriptions now explain the final fixes and link exact-head validation;
  #27/#35 titles reflect their final scope. #32 stays unchanged at `51898a8`.
- Next action: manual review of the four validated PRs and separate authorization
  before merging. Keep #32 open/blocked pending a separately selected licensing
  resolution. No further implementation milestone is selected. This aggregate
  handoff is a local documentation checkpoint; main was not pushed by this task.

### Deferred Avalonia PR #32

- Baseline: Dependabot head `51898a8`, Avalonia 12.1.6. Initial CI fails NU1605:
  Avalonia.FreeDesktop requires Tmds.DBus.Protocol >=0.94.1 while the app pins 0.92.0.
- A local diagnostic with app/test pins at 0.94.1 passed the Linux Release build
  (three obsolescence warnings, zero errors), 53 Linux GUI/protocol tests and 33
  portable Linux-specific tests using SDK 10.0.203. The pin edits were reverted
  after the user selected leaving this PR open and blocked; the bot proposal is
  preserved. These results do not describe the unchanged PR head.
- Exact Avalonia source `cf8e564674700348947e93ab19105f27afe859a9` retains
  [MS-PL Calendar code](https://github.com/AvaloniaUI/Avalonia/blob/cf8e564674700348947e93ab19105f27afe859a9/src/Avalonia.Controls/Calendar/Calendar.cs)
  and [MS-PL Fluent theme resources](https://github.com/AvaloniaUI/Avalonia/blob/cf8e564674700348947e93ab19105f27afe859a9/src/Avalonia.Themes.Fluent/Controls/Calendar.xaml),
  with default compile/resource inclusion. The exact source contains 19 marked
  controls C# files and seven marked Fluent XAML files (plus eight Simple themes).
  Its [NOTICE](https://github.com/AvaloniaUI/Avalonia/blob/cf8e564674700348947e93ab19105f27afe859a9/NOTICE.md)
  and top-level MIT license are byte-identical to the repository's retained files;
  preserving those notices does not establish AGPL compatibility. The
  [GNU license list](https://www.gnu.org/licenses/license-list.html#ms-pl) identifies
  MS-PL as GPL-incompatible. No reduced build or linking exception was found here.
- Status: leave #32 open and blocked. No dependency/catalog approval, license-guard
  bypass, merge or publication. A separately scoped reduced build/component review
  or applicable licensing permission is required before proceeding. Windows and
  native Flatpak success are not claimed. No live Immich access occurred.


## Dependabot completion check (2026-11-10, 20:39 Europe/Berlin)

- The first [NuGet updater](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487345)
  completed successfully and created five additional PRs (#32 through #36).
  All ten Dependabot PRs remain open and unmerged. All reported checks on their
  current heads have finished; five PRs have successful CI and five have failures.

| PR | Update | Head | CI result |
| --- | --- | --- | --- |
| [#27](https://github.com/VoltKraft/immich-folder-watch/pull/27) | download-artifact 7.0.0 to 8.0.2 | `27ab531` | Windows build/test job failed; remaining CI jobs passed |
| [#28](https://github.com/VoltKraft/immich-folder-watch/pull/28) | upload-artifact 6.0.0 to 7.0.2 | `339ee48` | All six CI jobs passed |
| [#29](https://github.com/VoltKraft/immich-folder-watch/pull/29) | deploy-pages 4.0.5 to 5.0.1 | `0c8975d` | All six CI jobs passed |
| [#30](https://github.com/VoltKraft/immich-folder-watch/pull/30) | configure-pages 5.0.0 to 6.0.0 | `383e170` | All six CI jobs passed |
| [#31](https://github.com/VoltKraft/immich-folder-watch/pull/31) | setup-node 6.5.0 to 7.1.0 | `9c6d43d` | All six CI jobs passed |
| [#32](https://github.com/VoltKraft/immich-folder-watch/pull/32) | Avalonia group, five updates | `51898a8` | Windows/Linux build/test and Flatpak preparation failed; native builds skipped; NuGet submission also failed |
| [#33](https://github.com/VoltKraft/immich-folder-watch/pull/33) | Microsoft.Extensions group, six updates | `7fb5e63` | Both native Flatpak builds failed; remaining CI jobs passed |
| [#34](https://github.com/VoltKraft/immich-folder-watch/pull/34) | SkiaSharp group, two updates | `a92df09` | All six CI jobs passed |
| [#35](https://github.com/VoltKraft/immich-folder-watch/pull/35) | xUnit group, three updates | `820cc9f` | Windows/Linux build/test jobs failed; remaining CI jobs passed |
| [#36](https://github.com/VoltKraft/immich-folder-watch/pull/36) | Microsoft.Data.Sqlite 10.0.10 to 11.0.0 | `4a26baf` | Both native Flatpak builds failed; remaining CI jobs passed |

- CodeQL reports neutral on all ten PRs, not a successful security scan.
  Failure causes were not investigated in this status-only check.
- Verified repository auto-merge remains disabled and every PR has
  `auto_merge: null` and no merge timestamp. No remote mutation, rerun or merge.
- Next action: investigate failed jobs and review compatibility/licenses before
  any separately authorized merge. Evidence is saved in a local documentation commit.

## First Dependabot run check (2026-11-10, 19:24 Europe/Berlin)

- Read-only GitHub inspection requested; no update PR was modified or merged.
- [GitHub Actions updater](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487560)
  completed successfully. The first [NuGet updater](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487345)
  is still running; no NuGet update PR exists at this snapshot.
- Created five open PRs: [#27](https://github.com/VoltKraft/immich-folder-watch/pull/27)
  download-artifact 7.0.0 to 8.0.2;
  [#28](https://github.com/VoltKraft/immich-folder-watch/pull/28)
  upload-artifact 6.0.0 to 7.0.2;
  [#29](https://github.com/VoltKraft/immich-folder-watch/pull/29)
  deploy-pages 4.0.5 to 5.0.1;
  [#30](https://github.com/VoltKraft/immich-folder-watch/pull/30)
  configure-pages 5.0.0 to 6.0.0;
  [#31](https://github.com/VoltKraft/immich-folder-watch/pull/31)
  setup-node 6.5.0 to 7.1.0. All are major-version proposals requiring review.
- PR CI is queued/running for all five; no failed check is reported at this
  snapshot. Packaging lint passed for #27/#29/#30. The successful updater run
  does not establish upgrade compatibility or completed PR CI.
- Verified repository `allow_auto_merge: false`, with `auto_merge: null` and
  no merge timestamp on all five PRs. No remote mutation was performed.
- Next action: recheck NuGet completion and PR CI, then review compatibility and
  licensing before any separately authorized merge. This check is recorded locally.

## Dependabot PR #36 license correction (2026-11-10)

- Scope: fix the existing Microsoft.Data.Sqlite 11.0.0 update PR's Flatpak CI
  failure without merging, changing product versions or weakening license checks.
- Baseline: `4a26baf`; both native Flatpak jobs stopped at the exact-version
  supplemental notice guard for Microsoft.Data.Sqlite.
- Inspected Microsoft.Data.Sqlite and Microsoft.Data.Sqlite.Core 11.0.0 archives:
  both declare MIT at the same recorded `dotnet/dotnet` revision and omit license
  text. Added an immutable version-specific MIT source and exact catalog entries;
  updated the top-level third-party summary. Native SQLite dependencies remain
  unchanged. Provenance is recorded in
  [the license review](../packaging/flatpak/licenses/README.md#microsoftdatasqlite-1100-review-2026-11-10).
- Validation: exact Flatpak SDK 10.0.401 restored Linux x64 and ARM64 into isolated
  caches. The generator's official-source/SHA-512 checks passed for the combined
  81-archive feed; the real license installer passed, and both new supplemental
  outputs match the upstream SHA-256. All 15 notice-installer regression tests
  passed, including rejection of unknown versions and modified notices.
- No application code changed. The existing Windows/Linux application CI passed
  before this metadata correction; actual native Flatpak rerun is still required.
- Next action: commit/push this correction to PR #36 and verify both native jobs.
  No PR has been merged and no release or live Immich operation was performed.

## Dependabot PR #35 compatibility repair (2026-11-10)

- User requested investigation and correction of failed Dependabot CI without
  merging. This worktree repairs PR #35 from `820cc9f` and retains its compatible
  xUnit 2.9.3 and Visual Studio runner 4.0.1 updates.
- Root causes: xUnit v3 framework 4.0.3 rejects the old assembly parallelism
  property, enables MTP v2 incompatible with the current .NET 10 VSTest command,
  and changes the extension ABI used by Avalonia.Headless.XUnit 12.0.3.
  A diagnostic `mtp-off`/new-parallelism experiment compiled but failed discovery
  for all 15 Avalonia GUI cases (`MissingMethodException`); 38 other tests passed.
- Correction: retain GUI framework 3.2.2 and its serial assembly setup, defer
  Dependabot `xunit.v3` proposals >=4 until a compatible bridge and runner path
  are validated, and use the predicate overload of `Assert.Single` for the newer
  xUnit v2 analyzer. No test was disabled or removed; no application code changed.
- License evidence: official NuGet package metadata for xUnit 2.9.3 and Visual
  Studio runner 4.0.1 declares Apache-2.0 with immutable source commits documented
  in the Linux test README. These test-only packages are AGPL-3.0-only compatible
  and do not enter application distribution artifacts.
- Validation: Release Linux GUI/protocol suite passed all 53 tests and the portable
  Core suite passed all 481 tests, with no failures/skips, using SDK 10.0.203,
  isolated headless controls and local D-Bus. Builds reported no warnings/errors.
  Dependabot schema, local documentation links and diff whitespace checks passed.
- Next action: verify Windows/full CI on the corrected PR head. No merge or live
  Immich operation is authorized or performed.

## Dependabot PR #33 license correction (2026-11-10)

- Scope: fix the existing Microsoft.Extensions 11.0.0 update PR's Flatpak CI
  failure without merging, changing product versions or weakening license checks.
- Baseline: `7fb5e63`; both native Flatpak jobs stopped at the exact-version
  supplemental notice guard, beginning with Microsoft.Extensions.Configuration.
- Reviewed all 32 changed Microsoft.Extensions/System 11.0.0 archives in the
  resolved feed against their recorded `dotnet/dotnet` source revision. Added
  version-specific MIT provenance and exact catalog entries, including four new
  transitive System packages. All upstream third-party notices are retained.
  Detailed source/hash and license-delta evidence is in
  [the license review](../packaging/flatpak/licenses/README.md#microsoftextensions-1100-review-2026-11-10).
- Validation: exact Flatpak SDK 10.0.401 restored Linux x64 and ARM64 into isolated
  caches. The generator's official-source/SHA-512 checks passed for the combined
  87-archive feed; the real license installer passed and all 32 updated license
  and notice outputs matched reviewed SHA-256 values. All 15 notice-installer
  regression tests passed, including rejection of unknown versions/tampering.
- No application code changed. The existing Windows/Linux application CI passed
  before this metadata correction; actual native Flatpak rerun is still required.
- Next action: commit/push this correction to PR #33 and verify both native jobs.
  No PR has been merged and no release or live Immich operation was performed.

## Dependabot PR #27 CI correction (2026-11-10)

- User authorized investigating/fixing existing PR #27 without merging. Its
  Windows CI failed `Sync_IgnoresExcludedFileDeletionsButPropagatesMediaDeletion`
  because one asset appeared twice in the trash requests.
- Cause: watcher and polling handlers both read the mapping before asynchronous
  tombstone persistence removed it. A per-path in-progress claim now gives one
  handler ownership until completion, including exceptional exits. Polling keeps
  missing mappings while a deletion is active or failed, preserving retryability.
- Added deterministic concurrent watcher/poll tests with paused persistence and
  injected persistence failure. Both assertions failed against the original
  production code; the initial guard passed the full 483-test Core suite.
  After independent review identified the polling retry gap, the corrected delta
  passed all five focused deletion cases (including the original three cases).
- Independent source review found no remaining actionable issue; handle-bound
  absence checks and watcher shutdown draining remain unchanged. Initial restricted
  MSBuild attempts failed without compiler diagnostics; permitted local runs passed.
- The updated download-artifact SHA retains the upstream MIT license, verified
  at `9000827ccba6bdab643e8b6fd33ac0654aef8333`. No dependency is added by this fix.
- Next action: push this correction to the existing PR and verify Windows/Linux
  and native Flatpak CI on its exact head. No merge, release or live Immich access.

## Dependabot activation (2026-11-10)

- Selected milestone: `M-DEPENDABOT-20261110`, extended by explicit user request
  to activate security alerts/updates and push configuration while disabling auto-merge.
- Starting state: clean local `main` at `8c8bab8`; remote default branch `main`
  remains at `64a9892`. API readback: vulnerability alerts enabled (HTTP 204),
  automated security fixes disabled/unpaused, repository `allow_auto_merge: true`.
- DB-AC04: Complete. Pushed configuration commit `8c8bab8` to `main` without
  force; GitHub's branch SHA and decoded `.github/dependabot.yml` content match
  the local commit/file. Security alerts were already enabled and remain enabled
  (HTTP 204). Enabled automated security fixes and independently read back
  `enabled: true`, `paused: false`. Disabled repository auto-merge and independently
  verified `allow_auto_merge: false`.
- Hosted evidence: GitHub queued the first [NuGet update run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487345)
  and [GitHub Actions update run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42874487560)
  for `8c8bab8`. Automatic NuGet dependency submission started. No Dependabot PRs
  existed at the check; no package upgrade or merge was performed.
- Checks: Remote content comparison and settings readback passed. Configuration
  retains the prior schema/coverage/review evidence. Application sources, versions
  and workflows are unchanged; no additional local runtime tests were needed.
- Next action: Review generated dependency/security PRs with the existing license
  and platform CI requirements. The initial bot runs and push CI are queued/running;
  their completion is not claimed. Activation is complete; no further milestone selected.

## Dependabot implementation (2026-11-10)

The following records the local checkpoint before the authorized activation above.

- Selected milestone: `M-DEPENDABOT-20261110`; local implementation complete.
- Baseline: clean local `main` at `64a9892`, whose merge commit includes PR #26
  and version-preparation commit `f7fef40`. The older version checkpoint below
  predates that merge; this task does not recheck release publication.
- Scope: NuGet and GitHub Actions configuration and maintenance documentation;
  no package updates, push, repository-setting changes or publication.
- DB-AC01: `.github/dependabot.yml` covers all nine tracked C# project manifests
  and all six GitHub Actions workflows. Related NuGet packages have family groups;
  each ecosystem checks weekly with at most five open version-update PRs.
- DB-AC02: PyYAML parsing and validation against the downloaded SchemaStore
  Dependabot 2.0 JSON Schema passed. Manifest coverage, 59 local documentation link
  targets and `git diff --check` passed. Independent review found no actionable
  issue in configuration, existing read-only PR CI or publication boundaries.
- DB-AC03: Development guidance, project brief, AGENTS and Unreleased changelog
  updated. The local checkpoint hash is provided in the chat handoff.
- Validation limits: No hosted Dependabot run, package upgrade, application build
  or runtime test was performed; application sources and workflows are unchanged.
  Initial sandbox download failed DNS resolution; permitted schema download passed.
  An obsolete upstream NuGet fetcher URL returned 404; review used current upstream
  C# discovery source instead. No production operation was attempted.
- Next action: when publication is authorized, push the checkpoint to the default
  branch through the normal review process and inspect the first hosted Dependabot
  jobs/PRs. Security-update repository settings were not changed or verified.
  No further milestone or Goal was started.

## Version preparation checkpoint (2026-11-10)

- Active milestone: `M-VERSION-MERGE-20261110`; version metadata prepared and
  locally verified. CI and the authorized merge follow this checkpoint.
- User authorized updating the version and then merging existing PR #26, replacing
  the earlier no-merge instruction. The normal automatic release pipeline follows
  successful main CI; publication must be verified separately.
- Baseline: clean branch at `225ce88631f376dee34aebe6480607d0b8da48ea`, matching
  origin; main remains `26a0de519ee4f7eae2e556b8da7726539d578594`.
- Current-head CI `42760864837` is successful after rerunning only the lint job
  that exceeded six hours during Ubuntu package retrieval. All six jobs are green.
- Selected version: `3.0.0`, because HTTPS-by-default requires migration of existing
  HTTP configuration. GitHub's latest published release is `v2.11.3`; no `v3.*`
  tag exists in the refreshed repository.
- Validation: canonical product/assembly/file versions, changelog date and exact
  generated AppStream content agree; AppStream offline validation and diff checks
  pass. Linux application build/analyzers pass with 0 warnings/errors. Independent
  review found no version/packaging blocker; remote `v3.0.0` is absent.
- Next action: validate all six CI jobs on the version-preparation commit, mark
  PR #26 ready and merge the exact validated head. The authoritative external
  state is the [PR checks and merge record](https://github.com/VoltKraft/immich-folder-watch/pull/26)
  and [release workflow](https://github.com/VoltKraft/immich-folder-watch/actions/workflows/release.yaml);
  this source checkpoint does not claim later publication. No new Goal was started.

## Directory race follow-up (2026-11-10)

The following records the completed remediation handoff before merge authorization.

- Selected milestone: `M-WATCH-ROOT-ATOMICITY-20261110`; complete. All six CI jobs
  pass on `a188722`; this final handoff changes documentation only.
- Baseline: clean local and remote PR head `d922bfa86df14408185e811e230167705354dc7c`.
  PR #26 is open, draft, unmerged, targeting `main`; existing branch is reused.
- Implementation checkpoint: `b1d2eee` pushed to the existing PR; initial CI
  exposed Windows-specific native call and test-fixture issues, corrected below.
  `eaccd17` corrects native Windows calls; `a188722` completes junction fixtures.
- User scope: completely close the remaining watch-directory race, with subagents
  and regression tests in the same PR. No merge or release.
- Ownership: native filesystem abstraction and platform tests; worker/API integration;
  independent security review. Parent owns records, integration checks and commits.
- WR-AC01: Pinned native Linux/Windows filesystem primitives and worker/API
  integration cover enumeration, absence, reads, downloads, exact-file cleanup,
  timestamps and both ends of directory moves. Roots outlive callbacks/retries.
- WR-AC02: Linux local and CI validation and Windows x64 runtime CI pass.
  Capability checks fail closed. The [watch-root contract](watch-root-security.md)
  documents retained Linux containers, bounded cache and Windows sharing locks.
- WR-AC03: 33 added regression cases (20 native, 5 API, 8 worker), including
  deterministic root/parent/leaf changes, same-fingerprint replacement cleanup,
  legacy content IDs, journal recovery, remote cleanup and shutdown lifetime.
- WR-AC04: Independent review found no remaining actionable source issue after
  corrections for identity, bounded handle caching, stale cleanup/album authority,
  retries and lifecycle. Implementation and tests are pushed to the same PR.
  Documentation and PR evidence are updated. All six application/packaging jobs
  pass, including native x86_64 and aarch64 builds/validation.
- Next action: review PR #26 and arrange an exact-commit Security Cloud scan when
  supported. No further implementation milestone selected. PR remains draft and
  unmerged; no release or stable repository publication occurred.
- Goal controls: no new Goal requested or started; prior run remains historical.

### Directory race validation (2026-11-10)

| Check | Result | Limits |
| --- | --- | --- |
| Portable Core suite | 481 passed, 0 failed/skipped | Linux x86_64, SDK 10.0.203; final album-cache revocation delta then passed 10 targeted album/security cases |
| Native focused suite | 20 passed, including LRU eviction with active leases and exclusive writer locks | Windows cases also pass in current CI; Linux-only cases retain platform scope |
| Linux GUI/protocol suite | 53 passed, 0 failed/skipped | Headless/local sockets and D-Bus; no live Immich |
| Linux application build/analyzers | Passed, 0 warnings/errors | Debug; generated branding remains ignored |
| Independent source review | Passed with no remaining actionable finding | Windows/UNC and ARM64 runtime are separate evidence requirements |
| Diagnostic full run | 468 passed / 4 failed before corrections | Fixed Linux writer-lock handling, retained-container assertions and friendly write-permission errors; subsequent full run passed |
| [Initial follow-up CI 42758835923](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42758835923) | Linux application tests/build and packaging lint passed. Windows build passed, Core 434 passed / 38 failed / 9 skipped; WPF 36 passed and Linux-project tests 34 passed / 19 skipped | Corrected explicit SYNCHRONIZE access, native handle-relative rename, junction command quoting and portable test path. Independent delta review and 20 focused Linux cases pass; Windows rerun required |
| [Windows correction CI 42759557792](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42759557792) at `eaccd17` | Native production failures resolved; Core 470 passed / 2 failed / 9 skipped; WPF 36 passed and Linux-project tests 34 passed / 19 skipped | Two junction test bodies passed but their recursive fixture cleanup failed; explicit nonrecursive junction cleanup is required before the final rerun |
| [Final CI 42760114840](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42760114840) at `a188722` | All six jobs passed. Windows: Core 472 passed / 9 platform skips, WPF 36 passed, Linux-project 34 passed / 19 platform skips, PowerShell security 7 passed. Linux: Core 481 passed and GUI/protocol 53 passed. Both builds 0 warnings/errors; lint, candidate preparation and native x86_64/aarch64 builds/validation passed | Actual UNC/ARM64 app runtime remains untested; the final documentation-only checkpoint does not change the validated code/tests |
| Repository handoff | Diff whitespace checks and 102 local documentation links passed; reviewed staged files contain no generated outputs | All scoped changes remain in the existing PR; no merge |
| Security Cloud rescan | Not executed; exposed connector still has no branch/commit selector | No finding was marked closed in the service; exact-commit scan remains outstanding |

## Previous security remediation handoff (2026-11-09)

This section records the earlier partial handoff; the follow-up above supersedes
its filesystem disposition and next action.

- Milestone: `M-SECURITY-REMEDIATION-20261109`; remediation pass delivered in draft PR #26, with one explicitly open residual finding.
- Goal run: requested and executed in chat `01a1c1ee-b279-76d2-8529-eaf116140007`, created
  2026-11-09; criteria SEC-AC01 through SEC-AC05 fixed in the selected brief. The user later
  explicitly reaffirmed subagent use; focused implementation and independent reviews
  were used. Completion permits explicitly documented unresolved findings. The remediation
  assignment is delivered; the filesystem finding remains explicitly open and
  the PR is not ready to merge.
- Baseline: refreshed `origin/main`, `26a0de519ee4f7eae2e556b8da7726539d578594`;
  initially clean. Working branch: `security/remediate-all-findings`.
- Discovery: 14 new findings (11 medium, 3 low) from completed repository scan
  `wfr_1cb38532afa4dc13e4acdc43f5953f4ebd3b4308486bbadb640050a3194de7fb`,
  target `3d41ef56b524b7acfa11559859fc0c7dab0daa73`, completed 2026-10-03.
  Direct repository-filtered finding lists returned zero; querying the exact scan
  returned all 14 with no further cursor. Full details contain no proposed patches.
- Workstreams: CI/publication credentials, API/transfer bounds, local config/runtime
  security and HTTPS policy, watch-root and remote-album authorization.
- User approved HTTPS-by-default with explicit HTTP exception and `xhigh` rescan.
- Checkpoints: `a303e95` contains reviewed CI hardening; `6e1a781` contains
  application remediation; `cf290b6` corrects the Windows SQLite fixture cleanup. All are pushed to the single
  [draft PR #26](https://github.com/VoltKraft/immich-folder-watch/pull/26), targeting `main`.
  No merge or release was performed.
- Current disposition: 13 findings addressed in code; one partially addressed
  (`csf_77f3e84ec9b70e5aff765235`, concurrent watch-directory replacement).
  Full mapping, compatibility changes and residual risks are in
  [the remediation record](security-remediation-20261109.md).
- Independent reviewers checked CI trust, native Linux storage, REST/download
  bounds, realtime adapters and album authority. Review-driven corrections cover
  redirect/buffering in SocketIO and stale authority after failed/offline/rapid
  folder renames. No remaining actionable issue in those reviewed fixes; the
  acknowledged handle-bound filesystem gap remains open.
- Next action: review the single PR; retain draft status until the open filesystem
  race is resolved and exact-commit security validation can be arranged. All six CI jobs passed on `cf290b6`; this final handoff updates documentation only.
  No additional milestone was selected.

### Security validation (2026-11-09)

| Check | Result | Limits |
| --- | --- | --- |
| Portable Core tests | 448 passed on final combined rerun; 0 failed/skipped | .NET 10.0.203 selected by `global.json`; Linux x86_64 |
| Linux GUI/protocol tests | 53 passed | Isolated headless UI, local sockets and D-Bus; no live Immich |
| Linux app build/analyzers | Passed, 0 warnings/errors | Debug build; generated branding not committed |
| Tooling/packaging | 97 Python tests passed, including real PowerShell security scripts and isolated signed Flatpak repository tests | Synthetic keys/artifacts only; no publication |
| Workflow validation | actionlint 1.7.12 passed; YAML parsed; independent CI review passed | No release/WinGet/Flathub dispatch executed |
| Filesystem/album security | Linked entries, ownership scope/restart, exact-ID and stale-ID handling covered | Path checks are not race-proof; Windows reparse/runtime acceptance outstanding |
| Rescan | Not executed: exposed Cloud connector has no documented PR branch/commit selector; no UI available and PR security-review feature disabled | Unchanged-main scan would not validate this branch; arrange exact-commit scan when supported |
| GitHub CI `42693673854` at `6e1a781` | Linux build/tests and packaging lint passed. Windows build passed with 0 warnings/errors; test job exposed pooled SQLite handles in the new ownership test cleanup | Added the repository-standard pool clearing after awaited operations; rerun passed in `42694315680`; Windows-specific 36 tests also passed |
| [GitHub CI `42694315680`](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42694315680) at `cf290b6` | All six jobs passed: Windows/Linux application checks, packaging lint, candidate preparation, and native x86_64/aarch64 packages. Windows: Core 439 passed / 9 platform skips; Windows-specific 36 passed; Linux-project tests 34 passed / 19 platform skips; full solution build 0 warnings/errors; 7 PowerShell security tests passed | Both native x86_64 and aarch64 candidate builds/validation and artifact uploads passed; actual ARM64/UNC app runtime not exercised |
| Superseded native run | Earlier x86_64 candidate could not fetch its replaced synthetic PR merge commit after a new push | No source/compiler failure; current run is authoritative |
| Native runtime limits | Actual ARM64/UNC runtime remains unavailable | Native ABI source inspection and package compilation do not establish runtime behavior |
| Worker follow-up | 54 passed, 1 existing test raced SQLite persistence; moved its database assertion after durable completion and worker stop; final combined rerun passed | No product behavior was changed to satisfy the timing assertion |
| Initial sandbox attempts | VSTest socket and GPG-agent startup were denied; approved isolated reruns passed | Environment failures were not counted as passing tests |
| Repository diff | `git diff --check` passed; 79 local documentation paths checked with no missing targets; final staged artifact review passed | Only task-owned sources/docs/tests are staged |

## Previous completed distribution handoff

- Template cleanup: Completed 2026-10-16. Initialized workflow records for the
  established project; preserved its README, implementation, product documents,
  and history. Do not repeat initialization cleanup.
- Last updated: 2026-11-07 (Europe/Berlin).
- State / scope: `M-FLATPAK-PAGES-20261107` complete. The signed repository is
  live at <https://voltkraft.github.io/immich-folder-watch/>.
- Implementation revision: `48e6be14ccf508385c4b1796842010c09e2d1fb4`, pushed to
  `main`; product version and published bundle inputs remain `2.11.3`.
- Latest verified result: [Pages workflow 42412670753](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42412670753)
  succeeded. Both live descriptors work, and isolated Flatpak clients downloaded
  both complete architecture refs with commit and summary verification enabled.
- Authorization / execution: The user explicitly approved the signing-key upload,
  push and Pages activation on 2026-11-07 after the initial automatic approval
  rejection. The secret and fingerprint variable are configured, Pages uses
  Actions with HTTPS, and its environment allows branch `main` and tags `v*`.
- Next concrete action: No remaining distribution setup. Future stable releases
  dispatch the repository workflow automatically. Preserve the signing-key backup;
  select any subsequent product milestone separately.
- Required input: None.

## Historical distribution Goal reference

- Goal requested for this assignment: No. No Goal was started.
- Actual Goal state in another chat: Not inspected; this document neither activates
  nor transfers a run. Query actual Goal controls if a continuation refers to one.
- Selected Goal milestone / criteria snapshot / budget: Not applicable.

## Progress and evidence

| Milestone / criteria | Status | Evidence / remaining work |
| --- | --- | --- |
| `M-TEMPLATE-MIGRATION-20261016`, `TM-AC01` through `TM-AC04` | Verified | Guarded apply and preservation/static checks passed; see historical validation record and local recovery bundle |
| `M-FLATPAK-PAGES-20261107`, `FP-AC01`/`02`/`03`/`05` | Verified | Implementation, real signed bundles, regression tests, review and docs complete |
| `M-FLATPAK-PAGES-20261107`, `FP-AC04` | Verified | Explicitly authorized setup and Pages deployment succeeded; live descriptors, both architecture downloads and signature verification passed |

## Flatpak distribution validation (2026-11-07)

| Check | Result / evidence | Limits |
| --- | --- | --- |
| Existing release inputs | GitHub API confirmed stable `v2.11.3`; x64 bundle 34,198,880 bytes, ARM64 bundle 30,983,120 bytes | Existing release assets were read/downloaded, not changed |
| Real repository generation | Both bundles imported and signed with fingerprint `4ED65AC1C14D559C721C7A8B44B33451708EAD7D`; complete site is about 87 MiB on disk at ignored `artifacts/flatpak-pages-preview/` | Local staging only; no Pages deployment |
| Real client discovery | Isolated `flatpak remote-add` with public key and `remote-info` resolved x86_64 commit `bdcfdb3e896ca6be8c9d0b93e5947884711e2c56da1da3a6cecbfcbe89200bcf` and aarch64 commit `86250534e754a0fa6c2d0ab1236bf87e862599416f0871d979e424ced402e30b` | No installation in the real user profile, runtime download or app execution |
| Python tooling tests | `python3 -m unittest discover -s tools/tests -p 'test_*.py' -v`: 90 passed, including seven new repository tests | Initial sandbox run failed because gpg-agent sockets were denied; rerun with approved isolated local execution passed |
| Repository integration regression checks | Signed multiarchitecture import, updates after complete repo replacement, unsigned-summary rejection, `.flatpakref` client consumption, malformed input/branch and size-limit rejection all passed | Synthetic fixture updates; real app update across published Pages versions not yet observed |
| Workflows and review | All workflow YAML parses; actionlint passed for all workflows; independent read-only review found no actionable defects; `git diff --check` passed | Pages workflow succeeded; environment permits `main` and release tags `v*` |
| New action licenses | Official upstream MIT licenses verified for configure-pages, upload-pages-artifact and deploy-pages | CI-only additions; no application dependencies changed |
| Remote activation | Completed after explicit consent: `FLATPAK_GPG_PRIVATE_KEY` Actions secret, matching `FLATPAK_GPG_KEY_ID` variable, Pages `build_type=workflow`, HTTPS enforced, environment branch `main` / tag `v*` | Private key never printed or committed; previous rejection is resolved |
| Pages publication | Build and deployment both succeeded in [run 42412670753](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42412670753) from `48e6be1` | Publishes existing `v2.11.3` assets; no product release or tag was created |
| Live HTTPS endpoints | HTTP 200 for index, `.flatpakrepo`, `.flatpakref`, public key, repo config, summary and summary signature | Evidence saved locally in ignored `artifacts/flatpak-pages-live-verification.json` |
| Live client verification | Fresh isolated `.flatpakrepo` client resolves both expected commits; a separate `.flatpakref` client downloads complete x86_64 and aarch64 apps from Pages, with `gpg-verify=true` and `gpg-verify-summary=true` | Used `--no-deps --no-related --no-deploy`; no real-user installation, runtime download or application execution; future-version update remains covered by the local integration regression test |
| GitHub packaging CI | `Lint Flatpak packaging` passed in [run 42412671037](https://github.com/VoltKraft/immich-folder-watch/actions/runs/42412671037), including repository tests | Broader application tests and native candidate builds were still running at handoff; no application code changed |
| Local application/desktop/Immich tests | Not run | Distribution-only change; live distribution was verified without application execution |

## Historical migration validation record

| Check | Result / evidence | Limits |
| --- | --- | --- |
| Initial Git state | Clean at migration baseline `3d41ef56b524b7acfa11559859fc0c7dab0daa73`; inspected with `git --no-optional-locks -C <repository> status --porcelain=v2 --branch --untracked-files=all` and both working/staged diffs | Local refs only; no fetch |
| Old agent provenance | All 37 old `.codex` tracked files match template commit `fe6db7f7e7e65f076b5dc0706fc6d46eba6de14b` | Confirms no target-specific profile customizations |
| Applied Markdown links, TOML, scoped diff, content preservation | Passed: 11 Markdown files, 90 local links/anchors, 35 TOML files / 34 roles; 298 unaffected original files retain identical SHA-256 hashes. Reports: local `inspection-after.json` and `integrity.json` in the recovery bundle. | Static checks; ignored artifacts, nested checkouts, and runtime data are outside the content manifest |
| Application builds/tests, packaging, desktop checks, live Immich | Not run for this documentation/configuration-only assignment | No runtime, UI, sync, installer, or service validation implied |
| Existing QA reports | Retained as historical evidence at their original revisions | Migration does not renew their sign-offs or fill blank acceptance rows |

## Open questions and blockers

| ID | Question / missing prerequisite | Impact and next action |
| --- | --- | --- |
| IFW-Q01 | Resolved: GitHub Pages Flatpak distribution selected on 2026-11-07. | See `M-FLATPAK-PAGES-20261107`. |
| IFW-Q04 | Resolved: explicit user consent received; secret upload, push, Pages activation and live validation completed. | No remaining activation blocker. |
| IFW-Q02 | Older README/architecture summaries call Flatpak tray support disabled, while detailed architecture, parity notes, and later changelog describe restricted tray integration. Some QA labels also predate current modes. | Pre-existing documentation discrepancy, outside this migration. Reconcile against code and actual desktop evidence in a separately selected task; do not infer runtime behavior from either summary. |
| IFW-Q03 | Native desktop acceptance and actual Flathub publication are not established by the inspected historical preparation record. | Keep the existing QA boundaries; verify only when the corresponding task and environment are authorized. |

## Completion and next handoff

- Historical workflow migration is complete at `4afa9f4`; recovery evidence remains
  in [the migration record](template-migration.md).
- `FP-AC01` through `FP-AC05` are complete; local and live evidence is recorded above.
- Deliverables: Repository generator/tests, Pages workflow and release dispatch,
  public signing key, installation/migration/operations documentation and CI wiring.
- Private recovery key: ignored `artifacts/flatpak-signing/private-key.asc`, mode
  0600 inside a mode-0700 directory. Public key only is included in Git.
- Checkpoint: Implementation `48e6be1` is published; this completion record and
  installation-document updates are saved in a separate documentation checkpoint,
  whose hash is recorded in the chat handoff. No version/tag change.
