# Configuration

Each source can upload new media, upload existing and new media, or synchronize
with Immich in both directions. Album mapping, file filters, and optional local
cleanup are configured per source; transfer order, retries, and logging are global.

The app reads YAML configuration from a per-user location:

- `%LOCALAPPDATA%\Immich Folder Watch\config.yaml` (Windows)
- `$XDG_CONFIG_HOME/immich-folder-watch/config.yaml` (Linux), falling back to `~/.config/immich-folder-watch/config.yaml`

Each Windows user has an independent config; the MSI does not create one automatically. The GUI writes this file on **Save and Apply**; on first launch without a config the GUI starts with empty fields.

For the sidebar layout introduced in 2.10.0, see the [desktop interface guide](user-interface.md).
The layout change requires no YAML or sync-state migration and preserves all existing settings.

On upgrade from a pre-1.7 service-based install, the legacy `C:\ProgramData\Immich Folder Watch\config.yaml` is copied once into the installing user's `%LOCALAPPDATA%`.

## Persistent Sync State

The app automatically creates one `sync-state.db` beside `config.yaml`. This is
a single per-user SQLite database shared by every entry in `watch.sources`; it is
not created inside any watched folder and does not require a YAML setting.

- Windows: `%LOCALAPPDATA%\Immich Folder Watch\sync-state.db`
- Linux: `$XDG_CONFIG_HOME/immich-folder-watch/sync-state.db`, falling back to `~/.config/immich-folder-watch/sync-state.db`
- Flatpak: `~/.var/app/io.github.voltkraft.immich-folder-watch/config/immich-folder-watch/sync-state.db`

The database separates records by Immich account context and watched source so
the same relative file name can safely exist in multiple sources. It stores file
metadata, transfer results, Immich asset and album identifiers, and persistent
deletion/move markers. It does not store the API key; account separation uses a
SHA-256 identifier derived from the API URL and key.

With an empty database, the first start performs the reconciliation required by
each source's sync mode and records only confirmed results. Subsequent starts
activate watching before reconciling local metadata in the background. Files
whose size and UTC modification time still match are not hashed, uploaded, or
downloaded. Changing an API URL or API key creates a different account context
and therefore requires a new bootstrap for that context.

Do not edit or copy the database while the app is running. Include it with the
configuration in per-user backups if retaining transfer history is important.

### Last Sync across sessions

Since 2.10.1, **Last Sync** is restored from `sync-state.db` before the worker
contacts Immich. The database retains the latest successful upload/download time
for each account context (API URL and API key), across all sources. It stores UTC;
the desktop displays local time. Successful transfers update this value immediately,
without waiting for application exit. Empty scans, failed or skipped transfers,
server checks, and metadata-only reconciliation do not advance it.

History is separate from individual file records, so removing a watched source,
deleting a local file after upload, or expiring a tombstone does not erase it.
Changing the API URL or key selects that context's history, or shows no previous
sync if none exists. A late completion from an earlier worker cannot replace the
new session's displayed timestamp.

The auxiliary history table is created automatically without changing the existing
schema-version-1 file records or YAML. On first creation only, the app seeds history
from the newest available synchronized-record timestamp per account, excluding
tombstones. This is a best-effort value for older installations: their records may
reflect metadata reconciliation, and already-removed records cannot be reconstructed.
From this update onward, only explicit successful transfers advance history.
Older binaries can still open the database but do not maintain this history.

History reads and writes use the existing state-database failure handling. A
database-open/read failure prevents the worker from starting; a failed history
write is not silently presented as a durable success. Back up the database along
with the configuration; rebuilding a corrupt or removed database loses its history.

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
      deleteAfterUpload: false # uploadNew/uploadAll only; permanent local deletion
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
  transferOrder: "newestFirst" # newestFirst (default) | oldestFirst
  batchIntervalSeconds: 5
  maxBatchSize: 25
  fileReadyTimeoutSeconds: 30

retry:
  maxAttempts: 5
  baseDelayMilliseconds: 500

logging:
  level: "Information"
  target: "eventLog" # eventLog | file
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
- `logging.logDirectory` must be an absolute filesystem path when `logging.target` is `file`.

## Notes

### Transfer order and status

The global **Transfer order** setting applies to every source and both transfer
directions. `watch.transferOrder` accepts `newestFirst` (the default) or
`oldestFirst`; empty or unrecognized values fall back to `newestFirst`.
Uploads use the local UTC last-modified time sampled when queued and are ordered
across ready queued files before selecting a batch. First attempts take priority
over retries; the selected timestamp order applies within each group. Downloads are ordered within
each source/album pull by the server's `fileModifiedAt`, falling back to
`fileCreatedAt` and then `createdAt`. Files with no timestamp come last;
equal timestamps retain queue/API order.
This does not interrupt a running transfer or reorder the source/album traversal.
Use **Save and Apply** to activate a changed order.

Existing configurations without `transferOrder` automatically use `newestFirst`
after upgrading to 2.9.0; no file or sync-state migration is required. Select
`oldestFirst` to process older pending media first. Timestamp ordering replaces
the previous queue arrival order.

Each source's **General** tab contains **Include subdirectories**, while its
**Advanced** tab contains **Delete local files after upload** (available for upload modes only). Moving the
controls does not change their saved values or deletion safeguards.

The **Permissions** section starts collapsed. Its heading retains the aggregate
check result and shows OK only when all listed permissions pass. Expand it to
inspect individual results.

**Sync status** shows **Inactive** without file counts, or the file being
uploaded/downloaded or last sync error followed by `(processed of total)`. Processed files include
successful, failed, and skipped attempts; an active file is not counted until its
attempt finishes. Upload progress spans successive batches while the ready queue
remains nonempty; retries becoming ready after the queue drains start a new cycle.
Downloads between upload batches do not reset the saved upload counters. Download
progress spans one scan of all sync sources, with the total growing as pending
files are discovered in each album. Counts remain available after completion but
are hidden while inactive. They reset when the next transfer operation starts;
empty scans retain the counts.
Errors remain visible after a failed operation, independently of server
connectivity checks. A later successful scan clears a recovered pull error even
when no downloads are needed. An empty scan does not clear an upload error.

### File selection

- File extensions are case-insensitive.
- Each source has its own `extensions` include list.
- Extensions without `.` are normalized automatically.
- `retry.maxAttempts` applies only to transient upload failures such as network errors, timeouts, rate limiting, and temporary server errors. Retries are delayed and placed behind newly detected files; permanent HTTP errors are not retried unless the file changes. `uploadAll` and `sync` sources can also retry during a later startup reconciliation.
- `watch.sources[].excludeDirectories` and `watch.sources[].excludeFileNames` use case-insensitive glob patterns.
- `excludeDirectories` are matched against the directory path relative to the source root. Use patterns like `private` or `**/cache`.
- `excludeFileNames` are matched against the file name only. Use patterns like `Thumbs.db` or `*.tmp`.
- New sources prefill the full set of Immich-supported media extensions (images, RAW formats, and videos). Edit these under the selected folder's **File filters** tab.
- In the Windows GUI, `Excluded Directories` is shown only when `Include subdirectories` is enabled, but existing values are preserved when the field is hidden again.
- `logging.target` controls where logs are written. Valid values:
  - `eventLog` (Windows default): writes to a dedicated **Windows Event Log** named "Immich Folder Watch". The MSI installer registers the log and source at install time. The GUI's **Open Logs** button opens Event Viewer directly to the dedicated log.
  - `file`: writes to a daily-rotated text file under `logging.logDirectory`. The GUI's **Open Logs** button opens the directory in the platform file manager.
  - `journald` (Linux default): writes systemd-formatted output to the system journal. **Open Logs** shows recent session entries without granting Flatpak access to host logs.
  - Missing, blank, or unknown values normalize to `eventLog`; the Linux host coerces unsupported targets to `journald`.
  - Fresh Linux UI settings use the platform XDG state directory for file logs. Existing absolute directories are retained; legacy relative directories are resolved against the configuration directory before editing.
  - If the Event Log source is not registered (e.g. xcopy or developer install), the app falls back to file logging and surfaces a warning in the UI.
- `watch.sources[].albumName` is optional. Leave it empty to upload files without assigning them to an Immich album.
- If `watch.sources[].albumName` is set, uploads are added to that album and the daemon creates the album automatically if it does not exist yet.
- `watch.sources[].syncMode` controls how the folder interacts with Immich. Valid values:
  - `uploadNew` (default): only upload files that appear in the folder while the app is running. Existing files are ignored. Matches the historical behavior of the app.
  - `uploadAll`: upload all files currently in the folder on start and keep uploading any new files added later. No files are ever downloaded from Immich.
  - `sync`: keep the folder and Immich bidirectionally in sync. Downstream changes are picked up in realtime via the Immich Socket.IO channel (on asset upload/trash/delete/update/restore and album create/update/delete), with a 10-second polling fallback whenever the socket is disconnected. Local files missing on Immich are uploaded; Immich assets missing locally are downloaded. Synchronization also handles deletions, moves, and subfolder changes:
    - **Deleting a file locally** moves the corresponding Immich asset into the Immich trash.
    - **Removing an asset from the remote source** removes its tracked local file
      after a complete successful pull. For a single-album source, removing the
      asset from that album is sufficient; for the all-albums source, this includes
      trashing or deleting the asset in Immich. Local removal is permanent and does
      not use the operating system's recycle bin or trash. Partial or failed pulls
      do not trigger this cleanup.
    - **Moving a file** between the parent folder and a subfolder (or between two subfolders) updates the asset's album membership on Immich to match.
    - **Creating a first-level subfolder** creates the matching Immich album; **deleting a first-level subfolder** trashes any still-tracked assets under it and deletes the Immich album. (Applies to the subfolders-as-albums variant described below.)
    - **Renaming a first-level subfolder** renames the matching Immich album via `PATCH /albums/{id}`; **renaming an Immich album** renames the matching local first-level subfolder on the next pull. The worker tracks album ids so renames are detected even when the display name changes. Conflicts (a folder or album with the new name already exists) are logged and left untouched instead of being merged automatically.
    - Two shapes are supported depending on `albumName`:
      - `albumName` **set**: flat single-album sync. All files in the source root are kept in sync with that one album. `includeSubdirectories` is forced off — subfolders are ignored.
      - `albumName` **empty**: subfolders-as-albums sync. The root folder mirrors all Immich assets that are not in any album, and each first-level subfolder mirrors the Immich album with the same name. New subfolders become new albums (and new Immich albums become subfolders) in realtime. `includeSubdirectories` is forced on.
  - Missing, blank, or unknown values normalize to `uploadNew`. Pre-2.3 configs therefore load unchanged and keep the previous upload-only behavior.
  - The mode is configurable per source under **Folders → General → Sync Mode**. The `Include subdirectories` checkbox is hidden when `sync` is selected, since the behavior is dictated by whether `albumName` is set.
  - When any source uses `syncMode: sync`, the GUI's **Verify Immich Access** check additionally requires the `asset.download`, `asset.read`, `asset.delete`, `albumAsset.delete`, `album.delete`, and `album.update` permissions on the API key (for pull, move, trash, remove-from-album, subfolder-delete → album-delete, and subfolder-rename → album-rename respectively). Upload-only configurations (`uploadNew` / `uploadAll`) do not need them.
- `watch.sources[].deleteAfterUpload` is an opt-in inbox mode for upload-only sources:
  - The default is `false`. When `true` with `uploadNew` or `uploadAll`, a local file is permanently deleted only after Immich confirms the upload and any requested album assignment, the file's size and UTC modification time are still unchanged, and the successful upload state has been written to `sync-state.db`.
  - Enabling it also cleans up older verified uploads from the shared state database when their current fingerprint still matches. Existing `uploadNew` files without a verified database entry and files changed after upload are never deleted.
  - A failed local deletion leaves the verified database entry intact. The worker retries during its five-second polling sweeps and after application restarts without uploading the file again.
  - The setting is ignored for `sync`, even if manually set to `true` in YAML. It deletes only the local file and never removes the Immich asset.
  - Deletion is permanent and does not use the operating system's recycle bin or trash.
- In the Windows GUI, a newly added source suggests the folder name as the album name once; if you clear the field afterwards, it stays empty.
- Relative watch-source paths are resolved against the directory that contains `config.yaml` at runtime.
- Existing `1.4.x` configs that still use top-level `watch.extensions` are migrated to per-source extensions when loaded and rewritten in the new format on the next save.
- Existing relative `logging.logDirectory` values still run after normalization; both GUIs rewrite them to an absolute path on the next successful save.
- `localization.language` selects the GUI language. `auto` picks German when the operating system UI culture is German and English otherwise. `en` and `de` pin the language. Missing, blank, or unknown values normalize to `auto`. The language can also be changed at runtime through **Settings → General → Language**, which writes the selected value back to this field on the next save.
