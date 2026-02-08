# Contributing Guide

## Development Setup

1. Install .NET SDK 8.0 or newer.
2. Clone the repository.
3. Restore and build:

```bash
dotnet restore
dotnet build ImmichFolderWatch.sln -c Debug
```

4. Run tests:

```bash
dotnet test ImmichFolderWatch.sln -c Debug
```

## Branching and Pull Requests

- Create focused branches for each change.
- Keep pull requests small and reviewable.
- Include tests for behavior changes when practical.
- Update docs when configuration, architecture, or operations change.

## Code Style

- Nullable reference types are enabled.
- Keep comments concise and in English.
- Keep log output in English.
- Use clear names and avoid over-abstraction.

## Commit Messages

Use clear commit messages with intent and scope, for example:

- `feat(watcher): add debounce support for file events`
- `fix(immich): retry transient 5xx uploads`
- `docs(config): clarify API URL format`

## Reporting Bugs

Please open a GitHub issue with:

- Environment details (OS, .NET runtime, Immich version)
- Minimal reproducible config (without secrets)
- Relevant log excerpts
- Expected vs actual behavior

## Security Issues

Do not open public issues for security vulnerabilities. See [SECURITY.md](./SECURITY.md).
