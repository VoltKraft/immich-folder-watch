# Project Brief

## Identity and outcome

- Project: **Immich Folder Watch** (`immich-folder-watch`), an existing desktop
  application for people uploading or synchronizing local media with Immich.
- Applicable domain: Software. CAD and 3D printing are not part of the current
  product; their retained guides apply only if future work introduces those domains.
- Product baseline: The checked-in version is `2.11.3` in
  [Directory.Build.props](../Directory.Build.props). This is not a fresh release
  or an assertion about deployed installations.
- Brief revision: `IFW-BRIEF-20261016-01`.
- Plan maturity: Existing implementation with established documentation. The
  workflow migration below is selected; no subsequent product milestone is selected.
- Active milestone: None; the migration milestone is complete (see status).
  No subsequent product milestone is selected.
- Implementation request / scope: The user's 2026-10-16 request to migrate the
  current template workflow into this established project without breaking it.
  This covers contributor documentation and agent configuration only.
- Requirement source: The current request, the pre-migration AGENTS.md, and the
  existing product documents linked below. Existing implementation is context,
  not proof that every runtime or desktop acceptance check has passed.

## Scope and boundaries

- Preserve application sources, user configuration/data, API behavior, dependencies,
  license/attribution, build/packaging/release automation, versions, and release history.
- Maintain API-only Immich integration; never write directly to Immich storage.
  Preserve per-user security and Linux portal folder access.
- Authorized location: This repository. Local recovery copies and scoped local
  checkpoint commits are covered by the user's migration and checkpoint instructions.
- External actions: No Immich request, live synchronization, upload, download,
  deletion, installation, publication, push, or release is authorized by this migration.
  Reading existing documentation does not grant those permissions.
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
The following requirements define only this migration and ongoing workflow.

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

No later product milestone is selected. On a subsequent continuation request,
use any concrete task supplied by the user; otherwise help select the next change
from current evidence. Do not treat a QA checklist or an old deployment plan as
blanket authorization to implement, publish, or run live synchronization.

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
