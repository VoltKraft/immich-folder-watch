# Configuration

The daemon reads YAML configuration from `config.yml`.

## Example

See [examples/config.example.yml](../examples/config.example.yml).

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
  logDirectory: "logs"
```

## Required Fields

- `immich.serverApiUrl` must be an absolute URL and must include `/api`.
- `immich.apiKey` must be a valid Immich API key.
- `watch.sources` must include at least one source.
- `watch.extensions` must include at least one extension.
- Numeric settings must be positive integers.

## Notes

- File extensions are case-insensitive.
- Extensions without `.` are normalized automatically.
- Relative paths are allowed but resolved by the host OS.
