# Contributor Workflow Migration - 2026-10-16

This record describes the documentation/configuration migration requested for
the existing Immich Folder Watch project. [Project status](status.md) owns the
actual completion and validation results; this file records provenance and scope.

## Sources and adaptations

- Target baseline: `3d41ef56b524b7acfa11559859fc0c7dab0daa73` on `main`;
  declared product version `2.11.3`.
- Template source: `Template-Repository` commit
  `994103b8f50101d137a555a7360d27acba01aca3`.
- Old `.codex` baseline: All 36 profiles plus config matched the template at
  `fe6db7f7e7e65f076b5dc0706fc6d46eba6de14b`; no project customizations were found.
- Preserve established project contracts; initialize brief/status from current
  evidence, retain all existing product history, and add only workflow links/notes
  to README and the Unreleased changelog. Do not bump versions or use a release
  commit subject for this migration.
- Replace generic long role instructions with 34 focused profiles. Retire the
  redundant `buffer_api`, `figma_to_html`, `orchestrator`, `project_manager`,
  `responsive_design`, `sql_expert`, and `task_breakdown` profiles with backup.
  Their relevant responsibilities are covered by the collaboration routing.
- Keep model/effort inheritance for substantive work; only mechanical inventory
  and documentation-check helpers select `gpt-6-luna` with `high` reasoning.
  Leave concurrency unset so the client chooses its default.
- Omit the source profiles' `sandbox_mode` keys: current official documentation
  says custom roles inherit parent permissions; such keys do not override them.
  Explicit read-only behavioral boundaries remain. See
  [official subagent configuration](https://learn.chatgpt.com/docs/agent-configuration/subagents?surface=app)
  (checked 2026-10-16). Syntax validation does not confirm client loading or model access.
- Preserve CAD/printing guidance as optional domain rules. No CAD model, slicer,
  print, or physical acceptance work is introduced into this software project.

The changelog follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
and releases retain [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html),
checked against their official sites on 2026-10-16. Released entries are preserved.

## Recovery

Local recovery directory, intentionally excluded from Git by the existing
`artifacts/` rule:

`artifacts/template-migration-20261016-111434/`

The completed bundle contains original replaced/retired files, before/after
SHA-256 manifests, the exact applied plan, source provenance, verification reports,
an operation journal, and `RESTORE.md`. It is local to this checkout; a clone does
not include it. The Git parent commit also retains all previously tracked content.

Existing affected files are locked against competing writes/deletion from hash
verification through mutation. New files use create-new semantics. A failure
leaves the journal and original copies for inspected manual recovery; no automatic
rollback may overwrite a later edit. Check current hashes and preserve subsequent
work before restoring individual files. Never reset the whole repository or
delete generated output, user data, or nested checkouts to reverse this migration.

## Verification boundary

The preservation manifest covers every file tracked by this checkout and any
nonignored untracked file at capture, excluding nested checkout contents. Ignored
build output, caches, personal runtime configuration, `.git` internals, and nested
checkouts are not content-scanned or modified. Git HEAD/index/config are separately
checked around the migration; the intentional local commit is the only history
addition. The live application and configured Immich service are not contacted.

Static checks cover Markdown references in changed documents, profile/config TOML,
role/default selection, retained release history, and the final scoped Git diff.
Existing product tests and QA records remain authoritative only for the revisions
they actually tested. The source template repository receives no tracked changes.
