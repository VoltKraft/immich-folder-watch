# Architecture

## Goals

- Watch local folders for new media files.
- Upload files through the Immich HTTP API.
- Keep upload and HTTP behavior isolated from watcher orchestration.
- Remain host-ready for Windows Service and Linux `systemd`.

## Solution Layout

- `ImmichFolderWatch.Core`
  - Configuration models and loader
  - Validation logic
  - Domain models and interfaces
  - File-readiness and batching primitives
- `ImmichFolderWatch.Immich`
  - HTTP client implementation for Immich API
  - Retry and transient error handling
- `ImmichFolderWatch.Daemon`
  - Console host and background worker
  - File watcher integration, debounce, and batch upload loop
  - Logging setup (console + file)
- `ImmichFolderWatch.Tests`
  - Unit tests for config parsing, readiness checks, and batching/dedup

## Runtime Flow

1. Daemon loads `config.yaml` (YAML, `YamlDotNet`) and validates values.
2. Daemon verifies Immich connectivity through a ping/lightweight endpoint.
3. Worker initializes one `FileSystemWatcher` per source folder.
4. File events are debounced to avoid partial/incomplete writes.
5. File readiness check attempts shared read access with timeout.
6. Ready files are deduplicated and queued.
7. Queue flushes on batch interval and/or max batch size.
8. Immich client uploads files via multipart endpoint with `x-api-key`.
9. Transient failures are retried with exponential backoff.

## Design Decisions

- API uploads only: no direct writes to Immich storage.
- Path deduplication is in-memory and runtime-scoped.
- HTTP integration is isolated for easy endpoint/schema adjustments.
- Startup validation is fail-fast with explicit log messages.

## Immich API Assumptions

The Immich API can evolve. The following assumptions are centralized in
`src/ImmichFolderWatch.Immich/ImmichApiRoutes.cs` and
`src/ImmichFolderWatch.Immich/ImmichAssetClient.cs`.

- Base API URL ends with `/api`.
- Ping endpoint candidates: `server/ping`, `server-info/ping`.
- Upload endpoint candidate: `assets` (multipart form upload).
- Multipart includes `assetData` and metadata fields used by current client.

If Immich changes endpoints or required multipart fields, update only the
Immich project while keeping the daemon and core layers stable.
