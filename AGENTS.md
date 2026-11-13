# Repository Guidance

## Project entry

Immich Folder Watch is an established .NET 10 desktop application for Windows
(WPF) and Linux (Avalonia). It watches and synchronizes local media through the
Immich API; it must never write directly to Immich storage. See
[README.md](README.md) for product usage and [the project brief](docs/project.md)
for the existing architecture, canonical specifications, and selected scope.
The project is initialized. Preserve its implementation, data, and history;
do not restart template onboarding or infer a new product plan from maintenance.

Before substantive project work:

1. Read [the project brief](docs/project.md) for scope, active milestone,
   requirements, acceptance criteria, and project-specific boundaries.
2. Read [the status](docs/status.md) for progress, evidence, blockers, and the
   next action. Verify relevant live state before relying on recorded progress.
3. Read the shared [documentation](docs/guidelines/documentation.md) and
   [collaboration](docs/guidelines/collaboration.md) rules.
4. Read every domain guide applicable to the task, including mixed work:
   [software](docs/guidelines/software.md), [CAD](docs/guidelines/cad.md), and
   [3D printing](docs/guidelines/3d-printing.md). CAD automation scripts also
   require the software guide. Read applicable nested repository instructions.

These are required reads, not optional links. Load detailed referenced evidence
when needed; do not reread unrelated archives on every continuation.
Use [document ownership and precedence](docs/guidelines/documentation.md#document-ownership-and-precedence)
to reconcile project decisions, defaults, and recorded state.

## From brainstorming to implementation

- For new project work, the user discusses an idea. Codex owns
  filling and maintaining the project brief, status, and project README; never
  require the user to fill out the templates or supply formal acceptance criteria.
- During brainstorming, explore options and ask only questions that materially
  affect the plan. Derive draft requirements, milestones, acceptance checks, and
  applicable domain rules from the discussion and available evidence. Keep
  alternatives and assumptions distinct from the user's chosen direction.
- Persist meaningful planning results in the existing documents when the active
  mode permits edits. If Plan mode or read-only restrictions prohibit writing,
  retain a self-contained proposed plan in the chat and disclose that it is not
  saved to the repository. Once edits are allowed, persist it before implementation.
- A request to implement or work on a concrete, selected plan is sufficient
  direction to record that plan and begin; do not require a separate form-filling
  or approval round.
  Carry forward existing decisions, select the first actionable milestone, and
  initialize status yourself. Ask only about unresolved essentials for dependent
  work, and do not implement merely because an idea was mentioned.
- Fill only what is relevant now. Mark irrelevant fields as not applicable and
  keep nonblocking unknowns explicit. Inspect tools and commands as needed; do
  not fabricate values to make the documents look complete.
- When beginning implementation of a concrete project, automatically perform the
  [one-time template cleanup](docs/guidelines/documentation.md#one-time-template-cleanup)
  and record completion in the status document. Skip it during brainstorming,
  template maintenance, or when already completed; respect writing restrictions.

## Working agreements

- Automatically select and use suitable agents when their contribution improves
  the task under the [collaboration rules](docs/guidelines/collaboration.md#automatic-agent-selection).
  No special prompt or manual agent selection is required. Keep simple tasks
  local, retain the default model for uncertain assignments, and coordinate
  exclusive access to shared applications.
- Follow established conventions, keep changes focused, and preserve unrelated
  user changes. Do not manually edit generated, vendored, or lock files unless
  required by the task; prefer modifying their source or generating tool.
- Derive tools, structure, and commands from checked-in files and verified
  environment state. Do not invent a stack, installed application, or capability.
- Keep requirements in the project brief and progress in the status document.
  Link to authoritative detailed specifications rather than duplicating them.
- Keep AGENTS.md current automatically throughout the project, without a separate
  user prompt. When project context, structure, tooling, responsibilities, or
  referenced workflows change, update its concise description and relevant links
  in the same change. This ongoing maintenance continues after template cleanup.
  Preserve all general working rules and required reading obligations; do not
  remove or weaken them while adapting project-specific guidance. Keep detailed
  requirements in the project brief and progress in the status document, and
  verify updated descriptions and links against the actual project state.
- Distinguish assumptions, user reports, prepared work, executed changes, and
  verified results. Record unknowns and their impact; continue independent work
  when missing information does not prevent it.
- Existing authorization remains valid. A short prompt grants no additional
  permission for external publication, unrelated resources, or machine operation.
- Before adding or updating dependencies, verify their licenses from
  authoritative sources against the repository license and intended distribution.
  Do not add incompatible or unverifiable dependencies. If needed for the task,
  explain the dependency, license concern, and compatible alternatives first.
- Write repository documentation, comments, docstrings, API documentation, TODOs,
  explanatory example text, logs, changelogs, and commit messages in English.

## Short prompts and goals

- Interpret "work on the project", "continue the project", and equivalent
  requests in the user's language as continuing the active milestone in the
  project brief. Choose the next useful, authorized action from verified state.
- Resolve missing context under the onboarding workflow above. A saved brainstorm
  is not a selected implementation plan. If the selected plan is ready but no
  milestone is active, select its first ready milestone and record the selection.
  Ready means its outcome, acceptance evidence, boundaries, and prerequisites are
  clear enough for the next action; resolve only missing essentials first.
  A concrete scoped task, such as template maintenance, proceeds within its own
  scope without initializing an unrelated project.
- After a milestone is completed, end that assignment with evidence and a next
  step. On a subsequent user continuation request, select the next ready milestone
  within the selected plan and recorded implementation scope, using its order and
  dependencies. If no clear next milestone exists, help resolve that choice;
  if the plan is finished, report
  completion instead of inventing work. Never use this rule to retarget an
  unfinished goal or bypass a prerequisite.
- Start Goal mode only when the user explicitly requests a goal. For a new goal,
  resolve the active milestone to its stable ID, concrete outcome, acceptance
  criteria, evidence requirements, and boundaries. Record this run's reference
  in the status document. Do not silently follow a changed active-milestone
  pointer or weaken criteria to finish. Surface material scope changes.
- A project document does not activate a goal or transfer an active goal to a
  new chat. Follow the available goal controls and their lifecycle rules; verify
  the actual goal state before continuing an existing run. If those controls are
  unavailable, disclose that and do not claim Goal mode is active.
- At completion, report evidence against the selected milestone. Do not
  automatically expand the assignment to later milestones. If blocked, record
  the missing prerequisite and the concrete next action needed to resume;
  continue independent work within scope when possible.

## Validation and handoff

- Automatically save work in the applications being used and create local Git
  commits at meaningful checkpoints under the
  [saving and commit rules](docs/guidelines/collaboration.md#saving-and-commit-checkpoints).
  This is standing authorization within the task scope; do not ask again for
  routine saves or local commits. Respect active mode and permission restrictions.
- Run the smallest relevant validation first; broaden checks when justified.
  Review the final diff and artifact set for unintended changes.
- Update relevant checks and documentation with behavior, interface,
  configuration, dependency, command, or operational changes. Follow the shared
  [documentation and release rules](docs/guidelines/documentation.md).
- Update the status after meaningful progress and before handoff: evidence,
  revision, checks and their results, unresolved questions, and next action.
  The uninitialized reusable template keeps brief/status uninitialized and
  CHANGELOG.md as an empty project scaffold, recording template-only work in Git.
  This repository is already initialized: later template-workflow updates must
  preserve its populated records and product history, and update its actual status.
- Completion requires the requested deliverables, relevant passing checks, and
  updated documentation. Disclose checks that failed or could not run. Digital
  validation alone does not establish physical fit, strength, or safe operation.

## Project-specific engineering rules

- Preserve the per-user security model, portal-based Linux folder access, .NET 10,
  and Windows/Linux compatibility unless the selected task explicitly changes it.
  Keep Core independent of UI/runtime hosts; keep HTTP and realtime API-version
  changes in `ImmichFolderWatch.Immich`, separate from watcher orchestration.
- Follow [development commands and test prerequisites](docs/development.md).
  Use the SDK selected by [global.json](global.json). The full solution/test
  workflow requires Windows; Linux uses the Avalonia host, portable Core tests,
  and Linux GUI/protocol tests. A documented command is not evidence of execution.
  Builds generate branding from `assets/branding/logo.svg`; .NET analyzers run
  during builds. No separate repository formatter or lint command is established.
- The Linux UI uses a source-built reduced Avalonia variant; follow the
  [framework build and audit contract](docs/reduced-avalonia.md). Preserve immutable
  source pins, exclusive private package mapping, exact compiler/provenance checks
  and offline reconstruction. Framework updates require source-level license review.
- Dependabot configuration in [`.github/dependabot.yml`](.github/dependabot.yml)
  covers NuGet and GitHub Actions. Follow the [dependency-update workflow](docs/development.md#dependency-updates)
  for license review, coordinated packaging pins and validation before merging updates.
- Use four-space C# indentation, file-scoped namespaces, PascalCase types/public
  members, camelCase locals/parameters, and `Async` suffixes. Preserve enabled
  nullable reference types, implicit usings, and analyzers in Directory.Build.props.
- Security regression coverage and known residual risks are tracked in
  [the security remediation record](docs/security-remediation-20261109.md). Preserve
  HTTPS-by-default policy, bounded transfers, exact-ID album authorization, and the
  [handle-bound watch-root contract](docs/watch-root-security.md) when changing sync behavior.
- Windows MSI upgrades must close the app or abort before old-product removal,
  and keep removal inside the rollback transaction. Preserve the compiled-MSI
  gate in `packaging/windows/Test-InstallerUpgradeContract.ps1`; follow the
  [upgrade validation contract](packaging/windows/README.md#upgrade-process-safety).
  Static/package checks do not establish a successful installed Windows upgrade.
- Tests use xUnit and Coverlet. Match platform scope, mirror production namespaces,
  name classes `*Tests`, and use descriptive case names. Add regression coverage
  for behavior changes. Await durable worker persistence before stopping workers
  or removing test databases, as described in the development guide. Avoid live
  Immich dependencies unless an integration check is explicitly scoped and authorized.
- Do not commit or manually edit generated `artifacts/`, `bin/`, or `obj/` output.
  Never commit API keys, private URLs, credentials, or sanitized-looking real secrets.
  Follow [SECURITY.md](SECURITY.md) for private vulnerability reporting. Verify
  dependencies against the repository's **AGPL-3.0-only** license and intended
  distribution; retain the existing attribution and license evidence.
- Prefer focused Conventional Commit subjects. PRs explain intent/user impact,
  linked issues, validation, and documentation/migration effects. Include screenshots
  for visible WPF/Avalonia changes. Keep independent changes separately reviewable.

## Project release procedure

[Directory.Build.props](Directory.Build.props) owns `<Version>` and corresponding
`MAJOR.MINOR.PATCH.0` assembly/file versions. Releases use stable
`MAJOR.MINOR.PATCH` and `vMAJOR.MINOR.PATCH` tags. Never reuse or alter a released
version. The compatibility contract covers user-visible behavior, configuration,
CLI options, persistent formats, and supported integrations. Increment MAJOR for
incompatible changes, MINOR for compatible features/capabilities, and PATCH for
compatible bug, security, documentation, packaging, or maintenance fixes.

Routine local checkpoints stay under `Unreleased` and do not bump product versions.
For an explicitly selected release, follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and the platform-specific [Windows](packaging/windows/README.md) and
[Flatpak](packaging/flatpak/README.md) instructions. From the repository root, run
`tools/release/bump-version.sh MAJOR.MINOR.PATCH`, complete its generated changelog
section, then run
`python3 tools/update-appstream.py MAJOR.MINOR.PATCH --metainfo packaging/flatpak/io.github.voltkraft.immich-folder-watch.metainfo.xml`.
Review all version references before a release commit with subject
`release: vMAJOR.MINOR.PATCH`. Reserve this subject for actual release preparation.
Prerelease identifiers or build metadata require adapting and validating all
release/packaging automation first. Local commits do not authorize publication.

GitHub Pages Flatpak distribution uses the existing published bundles; see the
[repository deployment guide](packaging/flatpak/pages.md). Keep its persistent
GPG identity, both architectures, signature verification and existing release
assets intact. Candidate builds must not be published to the stable repository.
