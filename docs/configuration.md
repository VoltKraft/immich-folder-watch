# Configuration

The daemon reads YAML configuration from `config.yaml`.

## Example

See [examples/config.example.yaml](../examples/config.example.yaml).

## Schema

```yaml
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "IMMICH_API_KEY"

watch:
  sources:
    - path: "C:\\Users\\<user>\\Pictures\\Screenshots"
      albumName: "Screenshots"
      includeSubdirectories: false
  extensions:
    - ".png"
    - ".jpg"
    - ".jpeg"
    - ".heic"
  batchIntervalSeconds: 5
  maxBatchSize: 25
  fileReadyTimeoutSeconds: 30

retry:
  maxAttempts: 5
  baseDelayMilliseconds: 500

logging:
  level: "Information"
  logDirectory: "C:\\ImmichFolderWatch\\logs"
```

## Required Fields

- `immich.serverApiUrl` must be an absolute URL and must include `/api`.
- `immich.apiKey` must be a valid Immich API key.
- `watch.sources` must include at least one source.
- `watch.extensions` must include at least one extension.
- Numeric settings must be positive integers.
- `logging.logDirectory` must be an absolute filesystem path.

## Notes

- File extensions are case-insensitive.
- Extensions without `.` are normalized automatically.
- Relative watch-source paths are resolved against the directory that contains `config.yaml` at runtime.
- Existing relative `logging.logDirectory` values still run after normalization, but the Windows GUI rewrites them to an absolute path on the next successful save.
