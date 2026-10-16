# Collaboration and Subagent Strategy

## Saving and commit checkpoints

Codex automatically preserves work throughout an authorized task. These rules
apply to every domain and to template maintenance, not only to software or CAD.

- Save edited files and native application documents after a meaningful work
  unit, before a risky operation or context/document switch, and before a planned
  pause, handoff, or completion. During long work units, use intermediate safe
  points regularly rather than leaving all progress unsaved until the end.
- Use the established project location and native editable format. Preserve
  recoverable versions before substantial changes; exports and screenshots do
  not replace native saves. Follow the project's artifact storage rules for
  large binaries, linked assets, or cloud documents.
- Verify the save using available application state, file evidence, or a saved
  revision. Do not assume autosave, a save request, or pending cloud sync has
  completed. Distinguish locally saved state from confirmed remote synchronization.
- Save only documents within the authorized work context. Respect active commands,
  foreign documents, and unrelated edits. If saving would lose data or overwrite
  unrelated work, preserve a separate authorized recovery copy when possible and
  resolve the conflict before proceeding with work that depends on that save.
- Create a local Git commit after a coherent planning/documentation checkpoint,
  implementation or construction step, verified fix, or milestone. Also commit
  meaningful outstanding work before a planned handoff. Use intermediate commits
  during lengthy tasks; do not wait for the entire project to be finished and do
  not create empty commits or a commit after every trivial edit.
- Before committing, save relevant sources, run appropriate checks, update affected
  records under [the handoff rules](../../AGENTS.md#validation-and-handoff), including
  their template-maintenance exception, and inspect the working tree and staged
  diff. Stage only task-owned changes. Do not sweep unrelated or pre-staged user
  changes into the commit, unstage them, or revert them to make the tree clean.
  If mixed changes cannot be safely isolated, report the specific blocker.
- Prefer coherent, validated commits. If unfinished work needs a recovery
  checkpoint, use an English commit message starting with `WIP:` and record what
  is incomplete, which checks failed or could not run, and the next action.
  A recovery commit is not a release or evidence of acceptance. Do not bypass
  hooks or other repository requirements to create it.
- Keep secrets, transient caches, and disallowed generated artifacts out of Git.
  A Git commit preserves only the staged repository content; reference the saved
  native revision or external artifact location when it is stored elsewhere.
- Verify the resulting commit and remaining working-tree changes. Report the
  checkpoint hash at handoff. Record it in the next normal status update when
  useful; do not create recursive commits just to record a commit's own hash.
- Routine local commits and saves need no repeated user confirmation. They do
  not authorize pushing, publishing, changing sharing settings, rewriting history,
  or force-pushing. Honor any existing explicit authorization for those actions.
- Respect Plan mode, read-only access, and actual tool availability. If Git,
  author identity, application access, or permissions prevent a checkpoint,
  retain all safely saved work and report the limitation; do not fabricate a
  successful save/commit, change global identity, or discard work to unblock it.
- In shared worktrees, the primary agent coordinates commits after integrating
  results. Subagents save their owned files and do not commit others' work.

## Objective

Quality takes priority over speed and cost. For each task, including brainstorming,
short continuation prompts, and goal work, automatically assess whether a
specialist, independent reviewer, or parallel investigation would improve the
result. When useful and available, invoke the agent without waiting for the user
to name it or request delegation. Keep trivial work with the primary agent when
a direct tool call or local edit is sufficient.

## Automatic agent selection

1. Inspect the roles actually exposed by the running client and their descriptions.
   The project definitions live in [`.codex/agents/`](../../.codex/agents).
   Do not assume an edited profile is already loaded into an existing session.
2. Split work only at useful boundaries with clear ownership and acceptance
   evidence. Select the most specific applicable role; do not chain overlapping
   specialists through the same task merely because they exist.
3. Use the routing below when a corresponding workstream is substantial enough
   to benefit. The primary agent coordinates the work; an extra orchestration
   layer is normally unnecessary.
4. If a necessary role is unavailable, use a suitable exposed role or a bounded
   ad-hoc assignment with the default model. If delegation itself is unavailable,
   continue directly and disclose any material limitation. Do not make manual
   agent setup a prerequisite for otherwise possible work.

| Workstream or trigger | Preferred assignment |
| --- | --- |
| Substantial planning, dependencies, or acceptance-criteria analysis | `enhanced_planner`; the primary owns project decisions and records. |
| Software implementation | Select the relevant language/domain specialist, or `fullstack_expert` for a tightly coupled end-to-end change; split only independent ownership. |
| UI implementation, supplied design conversion, or responsive behavior | `frontend_developer`; add `uiux_designer` or `design_system` for a distinct design decision or shared component system. |
| Schemas, migrations, or query plans | `database_architect`; avoid a second overlapping SQL assignment. |
| Uncertain external APIs, standards, catalogs, or asset licenses | `research_agent`, using current authoritative evidence. |
| Consequential code changes or security boundaries | An independent `code_reviewer` or `security_auditor` on a fixed revision/diff; use testing roles when meaningful tests are in scope. |
| Fusion construction or distributed assembly changes | `fusion_designer`; `python_expert` can prepare separate automation scripts under the software and CAD guides. |
| Printability, connections, material tradeoffs, or slicer preparation | `print_engineer` on an identified CAD revision. |
| Multipart delivery, critical interfaces, or CAD/print acceptance | Independent `cad_print_reviewer` against the complete requested package and authoritative BOM. |
| Substantial mechanical file/manifest comparison or local documentation-reference checks | `artifact_inventory` or `documentation_checker`, strictly within their limited contracts. |
| Documentation or illustrated assembly instructions | `doc_generator`, using actual source evidence and approved views. |
| Engineering executable pipelines, retries, or job dependencies | `workflow_manager`; this role designs project workflows, not a hierarchy of agents. |

For small CAD parts, one assigned worker can construct and prepare the part for
printing under both domain guides. Separate review when interfaces, assemblies,
or failure consequences warrant it; do not require every role on every task.
Likewise, language and infrastructure roles apply only to the project's actual
stack. Profiles do not mandate frameworks, new deliverables, or sprint rituals.

Keep role profiles short: selection trigger, responsibility, boundaries, and
evidence to return. Reusable technical rules remain in the domain guides. Put
lengthy repeatable procedures in on-demand skills or references when needed;
consult current official integration documentation instead of embedding a vendor
API manual in a general-purpose profile. Neither a role nor a skill creates tool
access or grants permission to publish, deploy, modify foreign resources, or run
a physical machine.

## Model and reasoning selection

Leave model and reasoning settings inherited from the client/parent by default.
This includes planning, implementation, CAD construction, print engineering,
research, and substantive reviews. Do not select a cheaper model merely from a
role name or price when its adequacy is uncertain, and do not pin an assumed
flagship as a replacement for the user's default.

Only the bounded, read-only `artifact_inventory` and `documentation_checker`
profiles explicitly select `gpt-6-luna` with `high` reasoning. They collect
mechanically verifiable evidence; they do not approve geometry, structural
behavior, security, compliance, requirements, or releases. Prefer deterministic
tools for counts, checksums, and reference matching. The primary checks their
evidence and owns conclusions; delegate only when the work warrants the overhead.

If a helper encounters ambiguous matching, missing authoritative inputs, or a
need for expert judgment, return the issue to the primary immediately. Continue
that work with the default model or an appropriate specialist instead of widening
the cheap helper's remit. If its configured model is unavailable, use the default
role/primary directly; do not block the project or change global settings.

Custom profile model/effort values take precedence over spawn settings; an
inherited value can be overridden at spawn. To escalate a pinned helper, move its
findings to the primary or an unpinned specialist rather than trying to override
the same profile. Use only supported client capabilities. See the official
[subagent configuration and model precedence](https://learn.chatgpt.com/docs/agent-configuration/subagents).
Do not claim measured quality or cost savings without actual task evidence.

Custom roles inherit the parent session's sandbox and approval policy. Their
instruction to remain read-only is a behavioral boundary, not a separate sandbox.
This project omits ineffective role-level `sandbox_mode` settings. Use the parent
permission controls and supported tool restrictions where needed; see the same
official configuration reference above.

## Parallelism and coordination

Run independent investigations, reviews, tests, and isolated implementation
workstreams in parallel when this improves quality or reduces wall-clock time.
Sequence dependent work and coordinate tasks that may edit the same files or
make conflicting decisions. Leave concurrency at the Codex default rather than
imposing a project-specific cap. Choose useful parallel work for quality, not
to minimize the number of agents, while respecting actual client limits and
shared-resource ownership. Reuse relevant agents instead of duplicating work.

Every delegated task must state its objective, scope, relevant context,
constraints, exact file/document ownership, expected deliverable, and validation
criteria. Tell workers they share the workspace and must preserve others' work.
Pass the relevant user decisions, domain guides, revision, and available tools.
The primary owns shared brief/status updates and commits unless explicitly
delegated; workers return evidence for integration. Avoid copying unrelated chat
history when a bounded handoff suffices.

Wait for all results required by the execution plan, resolve disagreements,
integrate dependent outputs, and perform a final cross-cutting review. Return
concise findings, changed artifacts, exact checked revision, checks/results,
limitations, and the next action. Respect requested validation exclusions and
report skipped checks; do not convert one task's exclusion into a permanent
project exemption.

## Shared CAD and slicer sessions

- The primary assigns one exclusive editor for a shared Fusion or slicer session.
  All agents, including the primary, respect that ownership. Separate documents
  in one UI do not make concurrent editing safe; only truly isolated sessions
  with independent resources can run in parallel.
- Other agents may research, prepare scripts in owned files, write documentation
  from fixed evidence, or inspect frozen exports while construction proceeds.
  Operations that change selection, active document, edit context, references,
  or command state also require session ownership, even when called inspection.
- Before a handoff, save and identify the native revision and recovery checkpoint,
  external-reference state, pending changes, and active commands. The new editor
  rechecks live state before acting. Follow the CAD guide's backup requirements;
  a prepared script or requested save is not execution evidence.
- Print preparation consumes an identified CAD revision. Geometry changes go back
  to its owner or require an explicit ownership transfer; re-evaluate affected
  exports and slicer work after a change. Reviewers use a fixed deliverable set.
- File-system read-only mode alone does not prevent external MCP/UI mutations.
  Keep reviewer tool access read-only where supported and explicitly prohibit
  application mutations. If safe inspection is unavailable, request evidence
  from the session owner and state the resulting review limitation.

## Primary agent responsibility

The primary agent remains responsible for understanding the complete request,
making architectural and cross-cutting decisions, selecting and coordinating
agents, validating important findings, resolving conflicts, and producing the
final result.

Treat subagent output as evidence, not truth. Verify important claims and use
independent review for high-risk or critical conclusions.
