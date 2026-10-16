# Documentation

These shared rules apply to every domain, including CAD and manufacturing
instructions. [The project brief](../project.md) owns intended behavior and
acceptance criteria; [the status](../status.md) owns progress and evidence.

- Always maintain changelogs according to the latest published version of
  [Keep a Changelog](https://keepachangelog.com/). The project changelog records
  concrete project changes; template maintenance follows the
  [template exception](../../AGENTS.md#validation-and-handoff).
- Always assign and increment project versions according to the latest
  published version of [Semantic Versioning](https://semver.org/) when preparing
  releases; routine checkpoints do not require a version bump.
- Verify the latest versions of both standards on their official websites
  when updating changelogs or project versions.
- Treat documentation as part of the implementation, not as optional follow-up
  work.
- Update documentation in the same change whenever behavior, public interfaces,
  configuration, commands, dependencies, or operational procedures change.
- Document public APIs, configuration options, environment variables, expected
  inputs and outputs, side effects, failure modes, and compatibility
  requirements.
- Provide migration guidance for breaking changes, renamed options, changed
  defaults, or persistent data-format changes.
- Keep examples minimal, realistic, secure, and executable when practical.
- Verify documented commands and examples against the current repository.
- Do not duplicate detailed information across multiple documents. Establish
  one source of truth and link to it from overview documents.
- Keep the README focused on orientation, setup, common workflows, and links to
  detailed documentation.
- Record significant architectural decisions and tradeoffs in an ADR or
  equivalent architecture document when the repository uses that practice.
- Keep generated documentation reproducible and modify its source rather than
  generated output.
- Remove or correct obsolete documentation instead of leaving contradictory
  guidance.

## Document ownership and precedence

- AGENTS.md owns the entry workflow and general agreements; domain guides own
  reusable technical rules. The project brief owns selected requirements,
  decisions, milestone order, and acceptance criteria. Status owns lifecycle,
  progress, evidence, blockers, and the next action. README summarizes and links
  to these sources; it does not define a separate plan or set of acceptance rules.
- Explicit user decisions override template defaults within their stated scope.
  Record project-specific exceptions and their source in the brief; keep the
  reusable rule and link to the exception instead of silently weakening it.
  Treat personal equipment and library defaults as user reports, not live checks.
- Reconcile contradictory current records using the user's decisions and verified
  evidence before dependent work. Correct stale summaries rather than maintaining
  two competing versions. Ask only when an unresolved choice affects the work.
  Keep a goal's historical starting contract distinct from current project plans.
- Keep handoff summaries short and link to detailed evidence. Do not copy the same
  check results into several tables: the validation record owns checks, progress
  maps results to criteria, and the handoff points to the relevant entries.

## One-time template cleanup

Run this automatically when the user requests implementation of a concrete
project and its plan is being persisted. No separate cleanup prompt is required.
Do not run it while maintaining the reusable template or merely brainstorming.
If the active mode prohibits edits, defer it until edits are allowed.

1. Read `Template cleanup` in [the status](../status.md). If it is `Completed`,
   skip initialization cleanup, including in new chats or later milestones. If
   the marker is absent, inspect existing project content and history first;
   do not reset or reinitialize an established project.
2. Populate the project brief and status from the selected plan. Rewrite the
   README for the actual project, replacing template advertising, copy/setup
   instructions, and template-maintenance examples with relevant project usage.
3. Remove obsolete fill-in instructions, sample-only rows, and placeholder
   explanations from the brief and status once their purpose is fulfilled.
   Replace the template-specific introduction in AGENTS.md with actual project
   context. Remove or adapt obsolete onboarding wording without removing the
   ongoing rules for planning, implementation, and documentation maintenance.
   Retain field labels needed for future handoffs, including plan maturity,
   implementation scope, active milestone, and the cleanup marker. Preserve
   durable rules in the guides rather than deleting them as fill-in hints.
4. Preserve AGENTS.md, its required reading links, all general working rules,
   domain guides, and agent configuration. Do not delete unused domain guides
   or whole directories merely because they came from the template. Preserve
   licenses, attribution, and actual project content, decisions, evidence, and
   history. The project changelog starts empty apart from its headings and format
   references. If an older template copy contains clearly identifiable template
   maintenance entries, remove those entries without deleting actual project
   changes or recording template cleanup as a product feature or release.
5. Retain genuine unknowns, open questions, and outstanding checks with their
   meaning and next action. Never treat every `TBD`, unfilled field, or empty
   result as disposable template text. Keep applicable requirements and stable IDs.
6. Review the diff and local links, verify that the general rules still apply,
   and record `Template cleanup: Completed` with the date and a brief summary in
   status only after these checks pass. Retain this marker in future status
   updates. Save and create a local checkpoint under the collaboration rules.

If interrupted, leave the marker pending and record the remaining steps. Resume
only those steps after inspecting current content; do not overwrite already
populated project documents. A save or commit limitation must be reported, but
does not justify rerunning successfully completed content cleanup.

## Releases and artifact revisions

- Keep unreleased changes under `Unreleased`; do not invent a release date,
  tag, or released version. Assign a Semantic Versioning version when preparing
  an actual project release and identify its authoritative version source.
- Define the public compatibility contract before deciding a version increment.
  For physical products, document the assembly, dimensional, or interchange
  interfaces that the project treats as that contract.
- CAD revision identifiers are separate from Semantic Versioning release numbers.
  Record which model, part, export, and manufacturing-profile revisions belong
  to a release; do not infer compatibility from a filename alone.
