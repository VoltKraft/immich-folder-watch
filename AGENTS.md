# Repository Guidelines

## Project Context and Structure

Immich Folder Watch is a .NET 10 desktop application for Windows and Linux. It watches local folders and transfers new media through the Immich HTTP API; it must never write directly to Immich storage.

Production code lives under `src/`:

- `ImmichFolderWatch.Core`: configuration, watching, synchronization, logging, and platform abstractions. Keep it independent of UI and runtime hosts.
- `ImmichFolderWatch.Immich`: Immich HTTP and realtime API integration. Isolate API-version changes here.
- `ImmichFolderWatch.App.Shared`: shared view models, models, services, and localized resources.
- `ImmichFolderWatch.App`: Windows WPF entry point and platform services.
- `ImmichFolderWatch.App.Linux`: Linux Avalonia entry point and portal integrations.
- `ImmichFolderWatch.Tests.Core`: portable xUnit tests; `ImmichFolderWatch.Tests`: Windows-specific tests.

Documentation belongs in `docs/`, packaging definitions in `packaging/`, branding sources in `assets/`, and maintenance utilities in `tools/`. Do not commit or manually edit generated output in `artifacts/`, `bin/`, or `obj/`.

## Working Agreements

- Derive behavior, tooling, and supported commands from checked-in code, manifests, and documentation; do not assume absent tools or frameworks.
- Follow established patterns, keep changes focused, and preserve unrelated user changes.
- Update tests and documentation in the same change when behavior, public interfaces, configuration, dependencies, or operations change.
- Avoid manual changes to generated, vendored, or lock files unless explicitly required. Modify the generator or source asset instead.
- Keep comments, logs, documentation, examples, changelog entries, TODOs, and commit messages in English regardless of the conversation language.

## Build, Run, and Test Commands

Use the SDK selected by `global.json` (currently .NET 10):

```bash
dotnet restore ImmichFolderWatch.sln
dotnet build ImmichFolderWatch.sln -c Debug
dotnet test ImmichFolderWatch.sln -c Debug
dotnet run --project src/ImmichFolderWatch.App
dotnet run --project src/ImmichFolderWatch.App.Linux
```

The full solution, including WPF tests, requires Windows. On Linux, use:

```bash
dotnet build src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj -c Debug
dotnet test src/ImmichFolderWatch.Tests.Core/ImmichFolderWatch.Tests.Core.csproj -c Debug
```

Building an app generates branding from `assets/branding/logo.svg`. There is no separate repository lint or formatting command; the current .NET analyzers run during builds. Consult `packaging/flatpak/README.md` and `packaging/windows/README.md` for packaging workflows rather than duplicating them here.

## Coding and API Documentation

Use four-space indentation and existing C# conventions: file-scoped namespaces, PascalCase types and public members, camelCase locals and parameters, and `Async` suffixes for asynchronous methods. Nullable reference types, implicit usings, and current .NET analyzers are enabled. Keep watcher orchestration out of HTTP implementations and runtime-host concerns out of Core.

Prefer clear names and simple structure over comments that narrate code. Comments should explain non-obvious reasons, invariants, edge cases, units, concurrency, security boundaries, performance tradeoffs, or external constraints. Describe workarounds with their cause and removal condition. Document public or complex APIs where contracts are not evident, including parameters, results, errors, side effects, nullability, thread safety, and lifecycle when relevant. Keep documentation beside the behavior and update both together.

Do not leave commented-out code or vague TODOs. A TODO must identify the missing work, why it remains, and a tracking reference when available. Simplify overly complex code instead of compensating with large comments.

## Testing and Validation

Tests use xUnit and Coverlet. Put tests in the project matching their platform scope, mirror production namespaces, name classes `*Tests`, and use descriptive method names such as `WaitUntilReadyAsync_ReturnsFalse_WhenTimeoutExpires`. Add regression coverage for behavior changes. Avoid live-Immich dependencies unless the test is explicitly documented as an integration check.

Run the smallest relevant test first, then broader checks justified by the change. Before completion, review the final diff for unintended edits and run the applicable build and test commands. Report exactly what ran and disclose skipped or unavailable checks. Work is complete only when the requested behavior, relevant validation, and required documentation are all addressed.

## Security, Compatibility, and Dependencies

Preserve the per-user security model, portal-based Linux folder access, and API-only Immich boundary. Never commit API keys, private URLs, credentials, or sanitized-looking real secrets. Follow `SECURITY.md` for private vulnerability reporting.

Before adding or updating a dependency, verify its license from an authoritative source against this repository's `AGPL-3.0-only` license and intended distribution. Do not add dependencies with incompatible or unverifiable licenses. If a requested dependency presents such a concern, stop and tell the user the package, license, conflict, and compatible alternatives. Preserve .NET 10 and supported Windows/Linux compatibility unless the task explicitly changes it.

## Documentation Standards

Treat documentation as implementation. Document public interfaces, configuration, environment variables, inputs, outputs, side effects, failure modes, and compatibility requirements when they change. Provide migration guidance for breaking changes, renamed settings, changed defaults, or persistent-format changes.

Keep examples minimal, realistic, secure, and executable, and verify commands against the repository. Maintain one source of truth: keep `README.md` focused on orientation and common workflows, then link to detailed documents instead of copying them. Record significant architectural decisions and tradeoffs in `docs/architecture.md` or an ADR if that practice is introduced. Correct obsolete or contradictory text rather than preserving it.

## Versioning and Releases

Follow [Semantic Versioning 2.0.0](https://semver.org/lang/de/) using stable `MAJOR.MINOR.PATCH` versions:

- Increment `MAJOR` for incompatible changes to user-visible behavior, configuration, command-line options, persistent formats, or supported integration contracts.
- Increment `MINOR` for backward-compatible features or meaningful capability additions.
- Increment `PATCH` for backward-compatible bug, security, documentation, packaging, or maintenance fixes that do not add a public capability.

Never reuse or alter a released version. `Directory.Build.props` is the source of truth for `<Version>`; corresponding assembly and file versions use `MAJOR.MINOR.PATCH.0`. Release tags use `vMAJOR.MINOR.PATCH`, where `v` is only a tag prefix. This repository's current release workflow publishes stable versions; introduce prerelease identifiers or build metadata only after adapting and validating all release and packaging automation.

Prepare a version with `tools/release/bump-version.sh MAJOR.MINOR.PATCH`, complete the generated `CHANGELOG.md` section, then run `python3 tools/update-appstream.py MAJOR.MINOR.PATCH`. Review every changed version reference and follow the platform-specific release instructions before committing with `release: vMAJOR.MINOR.PATCH`.

## Commits and Pull Requests

Prefer focused Conventional Commit-style subjects, for example `fix(immich): retry transient uploads` or `docs(config): clarify API URL`. Short imperative maintenance subjects also occur in history; whichever form is used, keep it specific and concise.

Pull requests should explain intent and user impact, link relevant issues, include appropriate tests, and identify documentation or migration effects. Add screenshots for visible WPF or Avalonia changes. Keep independent changes separately reviewable.

## Subagent Strategy

For each task, decide whether delegation would materially improve correctness, coverage, independent verification, or delivery time. Inspect currently available agents rather than assuming a fixed roster. Delegate only coherent, independently verifiable workstreams where the benefit exceeds coordination overhead, context loss, and edit-conflict risk.

Choose specialists by scope; use coordination or planning agents for multi-stage work when available, or create a purpose-built agent with a bounded objective if no role fits. Each assignment must state its scope, relevant context, constraints, expected result, and validation criteria. Select model capability and reasoning effort according to complexity, ambiguity, risk, and required confidence, and escalate if the work proves harder than expected.

Parallelize independent investigations, reviews, tests, or isolated edits; sequence dependent or overlapping work. Wait for required results, reconcile disagreements, and perform a cross-cutting final review. The primary agent remains responsible for the complete request, architecture and integration decisions, verification, conflict resolution, and final response. Treat subagent findings as evidence and independently verify important or high-risk claims.
