# Configuration

The app reads YAML configuration from a per-user location:

- `%LOCALAPPDATA%\Immich Folder Watch\config.yaml` (Windows)

Each Windows user has an independent config; the MSI does not create one automatically. The GUI writes this file on **Save and Apply**; on first launch without a config the GUI starts with empty fields.

On upgrade from a pre-1.7 service-based install, the legacy `C:\ProgramData\Immich Folder Watch\config.yaml` is copied once into the installing user's `%LOCALAPPDATA%`.

## Example

See [packaging/windows/config.windows.example.yaml](../packaging/windows/config.windows.example.yaml) for a standalone reference file.

## Schema

```yaml
immich:
  serverApiUrl: "https://immich.example.com/api"
  apiKey: "IMMICH_API_KEY"

watch:
  sources:
    - path: "C:\\Users\\<user>\\Pictures\\Screenshots"
      albumName: "Screenshots" # optional; leave empty to upload without album placement
      syncMode: "uploadNew" # uploadNew (default) | uploadAll | sync
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
  logDirectory: "C:\\Users\\<user>\\AppData\\Local\\Immich Folder Watch\\logs"

localization:
  language: "auto" # auto | en | de
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
- `watch.sources[].syncMode` controls how the folder interacts with Immich. Valid values:
  - `uploadNew` (default): only upload files that appear in the folder while the app is running. Existing files are ignored. Matches the historical behavior of the app.
  - `uploadAll`: upload all files currently in the folder on start and keep uploading any new files added later. No files are ever downloaded from Immich.
  - `sync`: keep the folder and its Immich album additively in sync. On start and periodically afterwards (every 60 seconds), local files missing in the album are uploaded and album assets missing locally are downloaded. **Deletions are not propagated** in either direction: removing a file locally does not delete the asset in Immich, and removing an asset in Immich does not delete the local file. `sync` requires a non-empty `albumName`.
  - Missing, blank, or unknown values normalize to `uploadNew`. Pre-2.3 configs therefore load unchanged and keep the previous upload-only behavior.
  - The mode is configurable per source in the Windows GUI (**Sync Mode** dropdown on each watched-folder card).
  - When any source uses `syncMode: sync`, the GUI's **Verify Immich Access** check additionally requires the `asset.download` permission on the API key. Upload-only configurations (`uploadNew` / `uploadAll`) do not need it.
- In the Windows GUI, a newly added source suggests the folder name as the album name once; if you clear the field afterwards, it stays empty.
- Relative watch-source paths are resolved against the directory that contains `config.yaml` at runtime.
- Existing `1.4.x` configs that still use top-level `watch.extensions` are migrated to per-source extensions when loaded and rewritten in the new format on the next save.
- Existing relative `logging.logDirectory` values still run after normalization, but the Windows GUI rewrites them to an absolute path on the next successful save.
- `localization.language` selects the GUI language. `auto` picks German when the Windows UI culture is German and English otherwise. `en` and `de` pin the language. Missing, blank, or unknown values normalize to `auto`. The language can also be changed at runtime through the **Appearance → Language** dropdown, which writes the selected value back to this field on the next save.
