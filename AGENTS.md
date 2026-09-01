# Repository Guidelines

## Project Structure & Module Organization

Production code lives under `src/`. `ImmichFolderWatch.Core` contains configuration, file-watching, and platform abstractions; `ImmichFolderWatch.Immich` owns Immich API integration; and `ImmichFolderWatch.App.Shared` provides shared view models and resources. The Windows WPF UI is in `ImmichFolderWatch.App`, while `ImmichFolderWatch.App.Linux` is the Avalonia/Linux host. Tests are split between portable `ImmichFolderWatch.Tests.Core` tests and Windows-specific `ImmichFolderWatch.Tests` tests. Documentation is in `docs/`, packaging definitions in `packaging/`, branding sources in `assets/`, and maintenance utilities in `tools/`. Generated output such as `artifacts/`, `bin/`, and `obj/` should not be committed.

## Build, Test, and Development Commands

Use the .NET SDK selected by `global.json` (currently .NET 10).

```bash
dotnet restore ImmichFolderWatch.sln
dotnet build ImmichFolderWatch.sln -c Debug
dotnet test ImmichFolderWatch.sln -c Debug
dotnet run --project src/ImmichFolderWatch.App.Linux
```

The full solution, including WPF tests, is built on Windows. On Linux, build `src/ImmichFolderWatch.App.Linux` and test `src/ImmichFolderWatch.Tests.Core` directly. Building either app automatically generates branding artifacts from `assets/branding/logo.svg`.

## Coding Style & Naming Conventions

Follow existing C# conventions: four-space indentation, file-scoped namespaces, PascalCase for types and public members, camelCase for locals and parameters, and an `Async` suffix for asynchronous methods. Nullable reference types, implicit usings, and current .NET analyzers are enabled. Keep Core independent of UI/runtime hosting and keep HTTP details in the Immich project. Comments, logs, and identifiers should be concise and in English.

## Testing Guidelines

Tests use xUnit and Coverlet. Place tests in the project matching their platform scope, mirror the production namespace, and name classes `*Tests`. Use descriptive methods such as `WaitUntilReadyAsync_ReturnsFalse_WhenTimeoutExpires`. Add regression tests for behavior changes and avoid tests that depend on a live Immich server unless explicitly documented as integration checks.

## Commit & Pull Request Guidelines

Prefer focused Conventional Commit-style subjects where practical, for example `fix(immich): retry transient uploads` or `docs(config): clarify API URL`. History also contains short imperative maintenance subjects; keep either form specific and concise. Pull requests should explain intent and user impact, link relevant issues, include tests, and update configuration or architecture docs when behavior changes. Add screenshots for visible WPF/Avalonia changes. Never include API keys, private URLs, or secrets; follow `SECURITY.md` for vulnerability reports.

