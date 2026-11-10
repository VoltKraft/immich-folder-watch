# Project Status

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
