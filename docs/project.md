# Project Brief

## Identity and outcome

- Project: **Immich Folder Watch** (`immich-folder-watch`), an existing desktop
  application for people uploading or synchronizing local media with Immich.
- Applicable domain: Software. CAD and 3D printing are not part of the current
  product; their retained guides apply only if future work introduces those domains.
- Product baseline: The checked-in version is `2.11.3` in
  [Directory.Build.props](../Directory.Build.props). This is not a fresh release
  or an assertion about deployed installations.
- Brief revision: `IFW-BRIEF-20261110-01`.
- Plan maturity: Selected follow-up to close the remaining filesystem race in PR #26.
- Active milestone: `M-WATCH-ROOT-ATOMICITY-20261110`.
- Implementation request / scope: The user's 2026-11-09 attached request to
  investigate every open Codex Security Cloud finding, consolidate verified fixes
  and documented unresolved items into one PR, and validate the result. The earlier
  distribution assignment remains preserved in its milestone and status history.
- Requirement source: The current request and existing packaging/release contracts.
  The completed contributor-workflow migration remains recorded below.

## Selected security remediation (2026-11-09)

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

No subsequent milestone is selected after the security remediation pass. Any continuation of this remediation should use the same PR and its documented residual filesystem work.

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
