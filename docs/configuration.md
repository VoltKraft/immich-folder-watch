# Configuration

The daemon reads YAML configuration from `config.yaml`.

## Example

See [packaging/windows/config.windows.example.yaml](../packaging/windows/config.windows.example.yaml).

## Schema

```yaml
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "IMMICH_API_KEY"

watch:
  sources:
    - path: "C:\\Users\\<user>\\Pictures\\Screenshots"
      albumName: "Screenshots" # optional; leave empty to upload without album placement
      includeSubdirectories: true
      extensions:
        - ".avif"
        - ".bmp"
        - ".gif"
        - ".heic"
        - ".heif"
        - ".jp2"
        - ".jpe"
        - ".jpeg"
        - ".jpg"
        - ".insp"
        - ".jxl"
        - ".png"
        - ".psd"
        - ".raw"
        - ".rw2"
        - ".svg"
        - ".tif"
        - ".tiff"
        - ".webp"
      excludeDirectories:
        - "private"
        - "**/cache"
      excludeFileNames:
        - "Thumbs.db"
        - "*.tmp"
  batchIntervalSeconds: 5
  maxBatchSize: 25
  fileReadyTimeoutSeconds: 30

retry:
  maxAttempts: 5
  baseDelayMilliseconds: 500

logging:
  level: "Information"
  logDirectory: "C:\\ProgramData\\Immich Folder Watch\\logs"
```

## Required Fields

- `immich.serverApiUrl` must be an absolute URL and must include `/api`.
- `immich.apiKey` must be a valid Immich API key.
- `watch.sources` must include at least one source.
- `watch.sources[].extensions` must include at least one extension for each source.
- Numeric settings must be positive integers.
- `logging.logDirectory` must be an absolute filesystem path.

## Notes

- File extensions are case-insensitive.
- Each source has its own `extensions` include list.
- Extensions without `.` are normalized automatically.
- `watch.sources[].excludeDirectories` and `watch.sources[].excludeFileNames` use case-insensitive glob patterns.
- `excludeDirectories` are matched against the directory path relative to the source root. Use patterns like `private` or `**/cache`.
- `excludeFileNames` are matched against the file name only. Use patterns like `Thumbs.db` or `*.tmp`.
- In the Windows GUI, new sources prefill the official Immich image-extension list and keep the advanced watch options collapsed by default.
- In the Windows GUI, `Excluded Directories` is shown only when `Include subdirectories` is enabled, but existing values are preserved when the field is hidden again.
- `watch.sources[].albumName` is optional. Leave it empty to upload files without assigning them to an Immich album.
- If `watch.sources[].albumName` is set, uploads are added to that album and the daemon creates the album automatically if it does not exist yet.
- In the Windows GUI, a newly added source suggests the folder name as the album name once; if you clear the field afterwards, it stays empty.
- Relative watch-source paths are resolved against the directory that contains `config.yaml` at runtime.
- Existing `1.4.x` configs that still use top-level `watch.extensions` are migrated to per-source extensions when loaded and rewritten in the new format on the next save.
- Existing relative `logging.logDirectory` values still run after normalization, but the Windows GUI rewrites them to an absolute path on the next successful save.
