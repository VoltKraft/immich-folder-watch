# Project Brief

## Identity and outcome

- Project: **Immich Folder Watch** (`immich-folder-watch`), an existing desktop
  application for people uploading or synchronizing local media with Immich.
- Applicable domain: Software. CAD and 3D printing are not part of the current
  product; their retained guides apply only if future work introduces those domains.
- Product baseline: The checked-in version is `3.0.2` in
  [Directory.Build.props](../Directory.Build.props). Published v3.0.2 at `df48398` includes
  all reviewed main changes; deployed installations remain separate evidence.
- Brief revision: `IFW-BRIEF-20261111-13`.
- Plan maturity: v3.0.2 published and verified; Avalonia remains deferred.
- Active milestone: none; `M-RELEASE-302-20261111` completed.
- Implementation request / scope: The user's 2026-11-10 request to implement
  Dependabot selects the repository configuration and maintenance documentation
  described below. Earlier security scope is retained as history: the user's
  2026-11-09 request to
  investigate every open Codex Security Cloud finding, consolidate verified fixes
  and documented unresolved items into one PR, and validate the result; the
  2026-11-10 follow-up explicitly requires complete directory-race remediation
  with subagents and regression tests in that same PR, without merging. The earlier
  distribution assignment remains preserved in its milestone and status history.
- Requirement source: The current request and existing packaging/release contracts.
  The completed contributor-workflow migration remains recorded below.

## M-RELEASE-302-20261111

Completed: v3.0.2 published from `df48398` with all four verified public assets.
Exact-revision CI/CodeQL and all release/distribution workflows passed; signed
Pages pulls verify 3.0.2 on both architectures. WinGet #477568 is submitted and
awaits external acceptance; Flathub builds pass with submission disabled. #32
remains open/license-blocked and auto-merge disabled. Final evidence is saved
locally after the published tag; no product changes remain unreleased.

The user explicitly authorized creating the current release with all new main
changes. Prepare and publish v3.0.2 from main `8d7afba`, including the previously
reviewed merges and documentation. This is a compatible patch release; preserve
configuration, persistence, platform support and the existing security contract.

Acceptance: consistent product/assembly/AppStream versions and release notes;
passing exact-revision CI and CodeQL; successful x64/ARM64 Windows MSI and
x86_64/aarch64 Flatpak release builds; immutable tag and complete public assets;
verified signed Pages distribution. Record WinGet submission and Flathub
preparation separately from external acceptance. Keep #32 open/license-blocked,
automatic merging disabled, and existing releases/signing identity intact.
[Release verification](release-3.0.2.md) owns execution evidence.

## M-DOC-PUBLISH-20261111

Completed: final evidence and related documentation were published as `ef6f394`.
Explicit CI 43025624807 passes all eight jobs, CodeQL 43025461040 passes all four
languages, and NuGet submission succeeds. The closing evidence update remains
documentation only, with identical product/workflow content. No release created.
[Publication evidence](dependabot-remaining-merges-20261111.md#documentation-publication-follow-up).

The user explicitly authorized publishing the final verification documentation
on main and checking CI. This includes the accumulated, related maintenance and
release-evidence history; the net change is documentation only. Preserve history
and existing safeguards, verify the pushed revision, and explicitly dispatch the
existing CI workflow because its path filter skips documentation-only pushes.
Keep #32 open/license-blocked and automatic merging disabled.

The user also asked whether a new release is worthwhile. Recommend a compatible
patch release, v3.0.2, based on the YAML string-preservation fix and reviewed
maintenance/dependency updates since v3.0.1. This recommendation does not select
version changes, a tag, release creation or publication. Existing release v3.0.1
remains immutable.

## M-REMAINING-MERGE-20261111

Completed: all seven selected PRs merged through `efeda2f`; final main CI,
four CodeQL analyses and NuGet submission pass. Automatic release follow-up
correctly skips existing v3.0.1. #32 remains open/license-blocked and auto-merge
disabled. [Final evidence](dependabot-remaining-merges-20261111.md).

The user explicitly authorized merging and checking the seven prepared PRs
#38/#39/#40/#42/#43/#44/#45. Reverify exact heads and successful checks, merge
without bypass or automatic merging, resolve integration conflicts without
losing reviewed changes, and verify final main CI/CodeQL and release follow-up.
Keep #32 open/license-blocked and auto-merge disabled. No version bump, new
release, manual deployment or publication of accumulated local documentation
is selected. Preserve local documentation history and record actual outcomes.

## M-REMAINING-PRS-20261111

Completed: all seven selected PRs are pushed, OPEN/CLEAN and pass their current
CI/CodeQL checks. Compatibility fixes, exact-source license notices and
independent SocketIO security review are recorded in the
[final verification record](dependabot-remaining-prs-20261111.md).
No merge or publication occurred; #32 remains excluded and auto-merge disabled.

The user selected work on all remaining open PRs except #32. Live inventory selects
#38 checkout, #39 github-script, #40 setup-dotnet, #42 Hosting, #43 SocketIOClient,
#44 Svg.Skia and #45 YamlDotNet, against main `a82216d`.

- Review exact upstream/source and transitive licenses before accepting upgrades.
- Refresh each PR without rewriting history, repair compatibility/packaging/CI
  issues and validate consequential changes with focused regression coverage.
- Require successful exact-head CI and CodeQL, or record a concrete blocker without
  weakening security or license requirements. Keep independently reviewable PRs.
- Push only the selected existing PR branches and update their evidence. No merge,
  release, deployment, live Immich access or auto-merge activation. #32 stays blocked.

## M-DEPENDABOT-IGNORE-20261111

Completed: #41 merged as `a82216d`; actual-parser reproduction and fresh hosted
NuGet run passed with the intended rule. Main CI/CodeQL passed. Separate
Dependabot duplicate-PR warnings and initial automatic rebase errors remain
recorded in [the verification report](dependabot-ignore-20261111.md); #32 remains
license-blocked and auto-merge disabled.

The user selected correcting the xUnit ignore requirement and verifying hosted
Dependabot NuGet runs. Prepare a scoped PR; default-branch execution follows
separate merge authorization after validation. The user then explicitly
authorized merging #41 and verifying the hosted NuGet runs; merge `a82216d`
activates the correction.

- Preserve the absolute xunit.v3 exclusion of versions >= 4.0.0, including its
  security-update scope; do not change package versions or other update settings.
- Validate YAML and the targeted diff, then verify the general NuGet job and
  existing Avalonia PR refresh no longer fail on the requirement parser.
- Record actual hosted outcomes and any independent blockers. Keep #32 open and
  license-blocked, automatic merging disabled and release v3.0.1 unchanged.

## M-PR34-MERGE-20261111

Completed: #34 merged as `eeba23d`; all eight main CI jobs and all four CodeQL
analyses passed. Release publication was correctly skipped. A separate pre-existing
xUnit ignore-range parse error was identified in automatic NuGet updater jobs;
it remains a maintenance follow-up, not an application CI failure.

The user authorized merging #34 and checking main. Merge only the verified head,
without bypassing checks; verify main CI, CodeQL and automatic release follow-up.
Keep #32 open/blocked, auto-merge disabled and published v3.0.1 unchanged.
Record actual results in [PR #34 evidence](dependabot-pr34-20261111.md).

## M-PR34-20261111

Completed: refreshed PR #34 at `1a4722c`; all 14 current-head checks succeeded,
branding/license review passed, and GitHub reports clean mergeability. Historical
queued Dependabot checks are not current-head checks; their internal cause remains
unknown. See [renewed evidence](dependabot-pr34-20261111.md). No merge or release.

The user selected refreshing and validating PR #34, without merging or releasing.

- P34-AC01: Integrate current main without force-pushing; preserve the build-only
  SkiaSharp 4.155.0 proposal and application runtime dependency isolation.
- P34-AC02: Renew exact-package license review and validate generated branding
  against the current main baseline, including PNG pixels and ICO frames.
- P34-AC03: Verify all current-head CI and CodeQL checks and investigate the
  separate Dependabot configuration validator. Record service limitations honestly;
  do not fabricate checks or weaken protection to clear a queued check.
- P34-AC04: Leave #32 open/blocked, auto-merge disabled and v3.0.1 unchanged.
  A merge requires a separate user decision.

## M-PR37-20261111

Completed: the user selected refreshing and validating PR #37 without merging.
Integrated current main, reviewed exact upstream MIT licenses/compatibility and
added a read-only CI artifact round trip with synthetic data. All eight CI jobs,
four CodeQL analyses and all 14 PR checks passed at `d79d3f3`.
See [PR #37 evidence](dependabot-pr37-20261111.md). Production deployment is not
claimed. Follow-up authorization: the user selected merging #37 and verifying
main CI/CodeQL. The merge was executed as `2a9a96d`; all eight main CI jobs and CodeQL passed.
#32/#34 remain deferred and
automatic merging stays disabled. Earlier no-merge scope below is historical.

- User selected completing the preparation of PR #37: update against current main,
  verify upstream licenses/compatibility and obtain successful CI/CodeQL. No merge.
- P37-AC01: Preserve the proposed SHA-pinned upload-pages-artifact v5 update and
  integrate current main without rewriting branch history or including #32/#34.
- P37-AC02: Exercise the actual Pages upload and artifact download using harmless
  fixtures; validate tar layout, bytes, hidden-file policy and dereferenced links.
  Use read-only repository permissions with no deployment, signing secret or Pages
  environment. Distinguish artifact validation from a real Pages deployment.
- P37-AC03: Verify all PR-head CI/CodeQL checks and record license/source evidence.
  Keep #32 blocked, #34 deferred, auto-merge disabled and release v3.0.1 unchanged.

## M-RELEASE-301-20261111

Completed: v3.0.1 published from `1ab0748`; exact-head CI/CodeQL, all four release
assets and signed Flatpak distribution verified. See [release evidence](release-3.0.1.md).
External WinGet acceptance and Flathub onboarding are not claimed as complete.

- User explicitly selected creation and publication of v3.0.1 containing all
  changes on main at baseline `bb13a33`. This authorizes release preparation,
  pushing the release commit and the existing release/distribution automation.
- R301-AC01: Bump unified product/assembly/file versions, complete release notes
  and regenerate AppStream metadata for 2026-11-11 (Europe/Berlin). Preserve
  prior releases, compatibility requirements and dependency license evidence.
- R301-AC02: Pass exact-commit CI and CodeQL, build all four Windows/Linux
  x64/ARM64 assets, and verify the immutable tag and published stable release.
- R301-AC03: Verify the signed Flatpak Pages distribution and report downstream
  WinGet/Flathub workflow results separately from external acceptance.
- R301-AC04: Leave #32 open/blocked, #34 open/deferred, automatic merging disabled;
  no additional dependency update, live Immich access or installed app changes.

## Release checkout hardening (2026-11-10)

- Follow-up authorization: push the validated fix to main and verify CI, CodeQL
  and both alert states. Keep #32/#34 open and automatic merging disabled.

- User requested verification and remediation of CodeQL alerts #11/#12 in
  `release.yaml`. Both flag repository script execution after the Flatpak job's
  dynamic checkout. Scope: focused workflow hardening, regression tests and docs.
- Require an explicit trusted default-branch checkout before Flatpak scripts run;
  reject a different release target before executing repository code, preserving
  matching source, SDK, offline dependency feed and manifest inputs.
- Preserve existing release gates, immutable target data, least-privilege tokens,
  versions and published assets. Keep #32 blocked, #34 deferred and auto-merge off.
- Validate the guard with real local Git histories and run workflow/manifest
  regression checks. Hosted CodeQL resolution requires a later published scan;
  do not dismiss alerts or trigger publication to manufacture that evidence.

## Selected dependency maintenance (2026-11-10)

### Documentation publication (2026-11-10)

- User explicitly authorized pushing the accumulated local documentation to main
  and verifying the resulting CI. This supersedes earlier local-only boundaries
  for the dependency-maintenance records.
- Publish the reviewed documentation history without rewriting remote history;
  verify CI and CodeQL on the pushed revision. Keep #32 open/blocked, #34
  open/deferred and automatic merging disabled.

### Remaining Actions PR merges (2026-11-10)

- User selected merging the successfully reviewed/refreshed #28/#29/#30/#31,
  leaving #34's configuration-check recovery open for now. This supersedes the
  earlier no-merge boundary only for these four Actions PRs.
- Verify exact heads/checks, preserve branch rules, merge manually, and verify
  final main CI. Leave #32 open/blocked and #34 open/deferred; retain disabled
  auto-merge. No version bump, manual release or publication workflow dispatch.
- Complete: all four merged; final main CI and CodeQL passed. #32/#34 stay open.

### Dependabot configuration-check recovery (2026-11-10)

- User authorized investigating and recovering #34's queued Dependabot-owned
  configuration check, preserving #32's block and disabled auto-merge; no merges.
- Validate the exact config, distinguish service dispatch from application CI,
  attempt a supported retry and, if unavailable, retrigger validation without
  changing configuration semantics. Verify the resulting current-head check plus
  CI/CodeQL; do not fabricate a status or weaken required checks.
- Outcome: repository validation passes; recovery is externally blocked on the
  owning GitHub service. See [diagnosis](dependabot-config-check-20261110.md).

### M-DEPENDABOT-REFRESH-20261110

- User explicitly authorized updating #28/#29/#30/#31/#34 with current remote
  main and obtaining successful CI and CodeQL checks. This supersedes the earlier
  read-only boundary for these branches only; keep PRs unmerged and auto-merge off.
- DCR-AC01: Preserve each reviewed proposal and integrate current main without
  force-pushing, altering unrelated branches or publishing local main records.
- DCR-AC02: Verify all six CI jobs plus CodeQL's four language analyses and
  aggregate assessment on each exact updated head. Investigate and correct scoped
  failures without disabling checks, assertions or license/security safeguards.
- DCR-AC03: Confirm #32 stays unchanged/open/blocked and auto-merge disabled;
  record exact revisions and evidence. No release, deployment or live Immich use.

### Remaining Dependabot review (2026-11-10)

- User selected a read-only remote review of #28, #29, #30, #31 and #34 for
  compatibility, authoritative license provenance and exact-head CI results.
- Compare proposed action/package changes with current use sites and distribution
  obligations; distinguish exercised CI paths from publication-only workflows and
  historical PR validation from integration with current main.
- Record findings and unresolved prerequisites locally. Do not merge, push PR
  changes, publish, or trigger deployment. Keep #32 open/blocked and automatic
  merging disabled. This review does not select a new implementation milestone.

### M-DEPENDABOT-CI-20261110

Updated authorization on 2026-11-10: merge the successfully validated PRs #27,
#33, #35 and #36. This supersedes their earlier no-merge boundary. Keep #32 open
and blocked, leave automatic merging disabled, preserve checks/branch rules and
verify the resulting merge records. Resolve any integration conflicts without
discarding reviewed changes; no release/version bump is selected.

- Original scope before the selective merge authorization: investigation and fixes for PRs #27, #32,
  #33, #35 and #36; no merges. Scoped corrections and CI validation stay on the
  existing PR branches, with no release/version bump or live Immich access.
- DCI-AC01: Identify failed-job causes on exact PR heads and preserve checks,
  security contracts, license guards and unrelated changes.
- DCI-AC02: Fix #27's concurrent deletion propagation with a deterministic
  regression; review exact Microsoft package license/notice sources for #33/#36;
  keep #35's test framework compatible with the Avalonia headless extension.
- DCI-AC03: Validate locally where applicable, independently review consequential
  fixes, push scoped commits to existing PRs and verify their CI before the separately
  authorized selective merges.
- DCI-AC04: Explicit follow-up decision: leave #32 open and blocked on Avalonia
  component licensing. Record technical downgrade failure and license evidence;
  do not approve the package or expand into a reduced Avalonia build.

- DCI-AC05: Merge only #27/#33/#35/#36 after successful exact-head checks;
  verify merge commits, keep #32 open and preserve disabled auto-merge.

### M-DEPENDABOT-20261110

- Outcome: Dependabot proposes reviewed updates for NuGet dependencies and pinned
  GitHub Actions, using weekly checks and bounded pull-request volume.
- DB-AC01: Cover all application/test projects and the branding generator, plus
  all GitHub Actions workflows. Group related NuGet packages to keep coordinated
  updates together; retain proposals for major upgrades for explicit review.
- DB-AC02: Validate configuration syntax/schema and manifest coverage; review
  compatibility with existing PR CI and preserve action SHA pins, read-only PR
  permissions, license review and platform validation requirements.
- DB-AC03: Document scheduling, review obligations, manually maintained packaging
  inputs and activation on the default branch. Update status and save a local commit.
- DB-AC04: The user's follow-up on 2026-11-10 authorizes pushing the configuration
  to the default branch, enabling Dependabot alerts and security updates, and
  keeping automatic merging disabled. Verify remote content and read back settings.
- Boundary: Configuration, documentation and the explicitly authorized GitHub
  settings/push only. No dependency/version changes or merging of update PRs.
  Disable repository auto-merge and preserve manual review. Hosted bot execution
  is separate evidence from successful activation and push.
- Canonical operational guidance: [Dependency updates](development.md#dependency-updates).

## Selected security remediation (2026-11-09)

Updated authorization on 2026-11-10: the user requested updating the version and
then merging PR #26. This supersedes the earlier no-version/no-merge boundary for
this PR. The existing successful-main-CI release automation remains in place and
will build/publish the new version after merge; no separate manual tag or release
dispatch is required.

### M-VERSION-MERGE-20261110

- Select `3.0.0`: requiring HTTPS by default changes the configuration contract
  for existing HTTP installations, so the repository's SemVer policy requires a
  major version. The currently published release is `v2.11.3`; `v3.0.0` is unused.
- VM-AC01: Update the unified product/assembly/file versions through the checked-in
  bump tool, complete changelog migration notes and regenerate AppStream metadata.
- VM-AC02: Review version consistency and release metadata; pass relevant local
  checks and all PR CI jobs on the exact version-preparation commit.
- VM-AC03: Mark PR #26 ready and merge the validated head without bypassing branch
  rules. Verify the merge and report the automatic release workflow separately
  from actual publication. Preserve the documented external rescan limitation.

The attached user request selects all open Codex Security Cloud findings for the
current repository, `VoltKraft/immich-folder-watch`, on the latest `main` baseline.
It authorizes one branch `security/remediate-all-findings`, scoped commits, a push,
and exactly one consolidated PR titled `security: remediate Codex Security Cloud findings`.
Use a draft if validation is incomplete or significant risks remain. Do not merge,
release, alter published assets, or contact a live Immich installation.

### M-SECURITY-REMEDIATION-20261109

- SEC-AC01: Retrieve every available open finding and full evidence across severities;
  inspect existing patches, deduplicate root causes, and record individual dispositions.
- SEC-AC02: Address actionable root causes with focused changes and regression tests;
  document unsafe-to-fix cases and residual risks without marking them fixed.
- SEC-AC03: Run relevant Linux portable/UI tests, builds/analyzers and workflow checks;
  independently review the combined diff. Windows-only checks require CI evidence.
- SEC-AC04: Rescan the updated commit/branch if the available service supports it;
  record target revision and any inability to scan the PR branch.
- SEC-AC05: Deliver one PR with all finding IDs/severities/dispositions, dependency,
  validation and rescan results, limitations and reviewer actions.
- Compatibility exception explicitly approved on 2026-11-09: require HTTPS by
  default; existing HTTP installations must explicitly opt into insecure transport.
  Preserve the option and provide migration guidance. No version/release bump here.
- Scan choice approved: the service's offered model with `xhigh` reasoning, as in
  the original scan. This is not a model choice for local subagents.

The historical distribution-only scope below describes the completed milestone;
security remediation additionally authorizes the application and CI changes above.

### M-WATCH-ROOT-ATOMICITY-20261110

The user explicitly requested complete remediation of `csf_77f3e84ec9b70e5aff765235`
on 2026-11-10, with subagents, regression tests and updates to existing PR #26.
This supersedes the prior partial-fix acceptance for this finding only. No merge,
release, version change, live Immich access or stable Flatpak publication.

- WR-AC01: Pin authorized root identity for the worker lifetime. Sensitive reads,
  deletion, download staging/finalization, timestamp changes and relevant directory
  operations must use no-follow handle-bound access, never a validated pathname
  reopened after an attacker can replace a component.
- WR-AC02: Retain Linux portal mounts and Windows compatibility; reject unsafe or
  unsupported filesystem operations before touching untrusted targets. No fallback
  to check-then-open paths is allowed at sensitive sinks.
- WR-AC03: Add deterministic race regressions for root/intermediate/leaf replacement,
  upload, cleanup and download lifecycle; verify outside sentinel contents and
  metadata remain untouched. Exercise Linux locally and Windows in CI.
- WR-AC04: Independently review the complete boundary and integrated call sites,
  pass relevant regression suites/builds, update documentation and the same PR.
  Native ARM64/UNC runtime and external rescan limits remain explicitly separate.

## Historical distribution scope and boundaries

- Preserve application sources, user configuration/data, API behavior, application
  dependencies, license/attribution, versions and release history. Extend only
  packaging/distribution automation for the selected milestone.
- Maintain API-only Immich integration; never write directly to Immich storage.
  Preserve per-user security and Linux portal folder access.
- Authorized location: This repository. Local recovery copies and scoped local
  checkpoint commits are covered by the user's migration and checkpoint instructions.
- External actions: The current distribution request covers configuring and
  publishing the requested GitHub Pages Flatpak repository and workflows using
  existing published bundles. On 2026-11-07 the user explicitly approved storing
  the private signing key as an Actions secret in `VoltKraft/immich-folder-watch`,
  pushing the changes, activating Pages, and verifying the live distribution.
  No new product release, tag
  replacement, Immich access, live synchronization or personal app installation
  is included. The older migration itself authorized no external publication.
- Keep `.git` configuration/history, nested checkouts under `worktrees/`, ignored
  build caches, and unrelated user changes intact. Do not launch the app against
  personal media to validate documentation.
- Dependency and distribution constraints: **AGPL-3.0-only**, with existing notices
  in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) and platform license catalogs.
  No dependency is added or updated by the migration.
- Generated artifacts: `artifacts/`, `bin/`, `obj/`, and packaging caches derive
  from tracked sources and tooling. Do not edit them manually. The migration's
  local recovery bundle under `artifacts/` is a separate ignored maintenance record.

## Requirements

Detailed product contracts remain in their existing authoritative documents.
The following historical requirements define the completed migration and ongoing
workflow. The current distribution requirements are in its milestone below.

| ID | Requirement | Source | Verification |
| --- | --- | --- | --- |
| IFW-WF-01 | Maintain project scope in this brief and actual evidence/next action in status; support short continuation prompts without manual forms. | User's template workflow and migration request | Entry/ownership/link review |
| IFW-WF-02 | Retain project-specific architecture, security, compatibility, licensing, test, and release rules alongside the general working rules. | Existing AGENTS.md and product documentation | Before/after instruction review |
| IFW-WF-03 | Use focused agents automatically when useful; inherit default model/effort except bounded mechanical helpers; leave concurrency at the Codex default. | Selected template configuration | TOML parsing and role/default comparison |
| IFW-WF-04 | Save work and create scoped local checkpoints; preserve unrelated files and recover originals of migrated files. | User's checkpoint and safe-migration instructions | SHA-256 manifest, backup, final diff, local commit |

## Milestones and acceptance

### M-TEMPLATE-MIGRATION-20261016 - Adopt the current contributor workflow

- Outcome: Initialized project records and current working rules/profile routing
  integrated with the established application, without changing product behavior.
- Requirements: `IFW-WF-01` through `IFW-WF-04`.
- Deliverables: [AGENTS.md](../AGENTS.md), this brief, [status](status.md),
  [shared guidelines](guidelines), [agent configuration](../.codex), README links,
  an Unreleased contributor-workflow note, and [migration provenance](template-migration.md).
- Dependencies: Inspect the existing checkout and protect current content before writing.
- Steps: Compare current rules, prepare a scoped overlay, review it, back up
  originals, apply guarded file changes, verify preservation, and checkpoint locally.
- Completion boundary: Documentation/configuration migration only. Runtime,
  desktop, packaging, and live Immich validation are not claimed or required by
  this documentation-only change. Future behavior changes retain normal test obligations.

| Criterion ID | Observable acceptance condition | Evidence |
| --- | --- | --- |
| TM-AC01 | Product sources, build/packaging configuration, version metadata, license assets, and existing detailed docs are unchanged; existing README/changelog content survives the additive notes. | Before/after hashes and scoped diff |
| TM-AC02 | Required reading, project-specific safeguards, saves/commits, cleanup, ongoing AGENTS maintenance, short prompts, and explicit Goal lifecycle are coherent. | Independent review and local link checks |
| TM-AC03 | The resulting 34 roles/config parse; default inheritance, the two bounded helper overrides, and absence of a project concurrency cap match the selected template. | TOML/static comparison; no claim of live client reload |
| TM-AC04 | Original replaced/retired files are recoverable; status distinguishes actual checks from historical QA and defines a truthful next action. | Recovery manifest, final review, local checkpoint or disclosed save limitation |

### M-FLATPAK-PAGES-20261107 - Add an updateable Flatpak repository

- Outcome: A signed, multiarchitecture OSTree repository on GitHub Pages, with
  `.flatpakrepo` and `.flatpakref` entry points, while retaining release bundles.
- Distribution branch: Preserve the published bundles' `master` Flatpak branch;
  only published stable SemVer releases may feed it (not CI candidate builds).
- Automation: Import both architecture bundles from the latest published release;
  serialize deployments and refuse stale/manual older-release publication.
  Explicitly dispatch after releases created by `GITHUB_TOKEN`.
- Trust: Use a persistent repository-specific GPG key, sign commits and summary,
  and embed its public key in both installation descriptors. Never commit private keys.
- Storage: Rebuild the current snapshot from published bundles; no historical
  repository or generated binary Git branch. Enforce the Pages 1 GB site limit.
- Acceptance: `FP-AC01` real signed two-architecture import and descriptor validation;
  `FP-AC02` isolated client signature verification and update discovery;
  `FP-AC03` automated tests and workflow review, preserving existing release assets;
  `FP-AC04` deployment and live descriptor/repository checks, or explicitly recorded
  external blocker; `FP-AC05` setup, migration, recovery and installation docs.
- Completion boundary: No app behavior or product-version change; no Flathub
  submission changes, native UI test, or connection to Immich is required.

The security and distribution milestones above preserve their historical scope.
The current selected work is the dependency-maintenance milestone above.

## Structure and tools

| Area | Responsibility / authoritative source |
| --- | --- |
| `src/ImmichFolderWatch.Core` | Configuration, watching, sync state, logging, platform abstractions; independent of UI/runtime hosts |
| `src/ImmichFolderWatch.Immich` | Immich HTTP and realtime integration; isolates API-version changes |
| `src/ImmichFolderWatch.App.Shared` | Shared view models, models, services, localization |
| `src/ImmichFolderWatch.App` | Windows WPF host and platform services |
| `src/ImmichFolderWatch.App.Linux` | Linux Avalonia host and portal integration |
| `src/ImmichFolderWatch.Tests.Core`, `src/ImmichFolderWatch.Tests`, `src/ImmichFolderWatch.Tests.Linux` | Portable, Windows-specific, and Linux GUI/protocol tests respectively |
| `packaging/`, `assets/`, `tools/` | Distribution definitions, authoritative branding sources, maintenance/build utilities |

The required SDK is selected by [global.json](../global.json): `10.0.100` with
`latestFeature` roll-forward. This is a repository requirement, not confirmation
of an installed SDK. Inspect available runtimes/tools before using them.

### Commands and manual workflows

Run project commands from the repository root. [Development](development.md)
owns restore/build/run/test commands, test prerequisites, branding generation,
and CI relationships. The complete solution uses Windows; Linux work uses the
Avalonia app plus both portable and Linux GUI/protocol test projects. Isolated
D-Bus tests need the Linux tools documented there. Build/restore can write caches
and retrieve dependencies; running the app can access configured media and Immich.
There is no separate established lint/format command; builds run .NET analyzers.

Packaging procedures remain in the [Windows](../packaging/windows/README.md),
[Flatpak](../packaging/flatpak/README.md), [WinGet](../packaging/winget/README.md),
and [Flathub](../packaging/flatpak/flathub/README.md) guides. Release preparation
and stable-version compatibility rules are in [AGENTS.md](../AGENTS.md#project-release-procedure).
Do not duplicate their command lists or run publication as routine validation.

## Canonical specifications and evidence

- [Architecture](architecture.md): component boundaries and significant design decisions.
- [Configuration](configuration.md): settings, modes, permissions, persistence,
  and deletion semantics. Bidirectional sync has consequential deletion behavior.
- [User interface](user-interface.md), [Windows installation](installation-windows.md),
  [Linux installation](installation-linux.md), and [troubleshooting](troubleshooting.md).
- [Linux parity](qa/linux-parity.md), [smoke checklist](qa/linux-smoke.md), and
  [Flathub preparation](qa/flathub-preparation.md): historical evidence and explicit
  remaining acceptance boundaries; recheck their dates/revisions before relying on them.
- [Migration record](template-migration.md): source revision, adaptations, recovery,
  and verification limits. Current progress belongs only in [status](status.md).

## Decisions and assumptions

| ID | Decision / assumption | Source and impact |
| --- | --- | --- |
| IFW-D01 | Existing product specifications take precedence over generic template defaults. | Migration request to preserve the started project; no stack or architecture reset |
| IFW-D02 | CAD/printing profiles and guides remain available but are not applicable to current application work. | Existing software-only scope; no new fabrication work |
| IFW-D03 | The imported role files omit `sandbox_mode`; permissions remain inherited from the parent. | Current official configuration documentation linked in the migration record; read-only instructions still bind review roles |
| IFW-D04 | No next product milestone is inferred from historical QA/publication documents. | No selected subsequent plan found in the inspected repository; resolve the user's next desired change first |
