# Troubleshooting

Start with **Overview** for connection and synchronization status, then use
**Open Logs** for details. The [desktop interface guide](user-interface.md)
explains the controls for each folder's sync mode, filters, and global settings.

## App tray shows "Server offline"

- Check `immich.serverApiUrl` ends with `/api`.
- Check `immich.apiKey` value is valid.
- Verify the Immich server is reachable from this machine. The app keeps retrying in the background and recovers automatically once the server is reachable again.

## Files are detected but not uploaded

- Confirm the file matches the relevant `watch.sources[].extensions` list.
- Check that the file does not match `watch.sources[].excludeDirectories` or `watch.sources[].excludeFileNames`.
- Check read permissions on watched files.
- Increase `watch.fileReadyTimeoutSeconds` for slow writes.

## Upload returns HTTP 401

- API key is missing or invalid.
- Regenerate API key in Immich and update `config.yaml`.

## Existing files or Immich assets are not synchronized

- The default **Upload new files only** mode ignores existing local files. Select
  **Upload everything in the folder** to include them at startup.
- Upload modes never download. Select **Sync folder with album (bidirectional)**
  to transfer in both directions, then use **Save and Apply**.
- Check album mapping: a named album synchronizes only that album with the source
  root. With no album name, first-level subfolders represent albums and the root
  represents media outside albums.
- Run **Connection → Verify Immich Access** after changing modes; bidirectional
  sync requires additional API permissions. Verify local write permission and
  available space when downloads fail.
- Bidirectional sync propagates deletions too. Review the
  [sync rules](configuration.md#file-selection) before enabling it.

## Downloads repeatedly fail with "Access to the path ... .downloading is denied"

This is a local write failure when creating the temporary download file. It is
separate from an Immich connection or API-key error. Failed downloads remain
pending, which is why the same files can appear again in subsequent sync cycles.

- Confirm that the signed-in desktop user can create and remove a file in the
  actual destination folder, including the affected album subfolder. Check its
  ownership, permissions, ACLs, and whether the filesystem is mounted read-only.
- With Flatpak, open **Folders**, select the affected folder again with **Choose Folder…**,
  and use **Save and Apply** to renew the portal selection. Host filesystem
  permissions and the portal's write grant must both allow access; selecting a
  folder again cannot repair host permissions.
- If only one filename fails, inspect any existing `<filename>.downloading` file
  and its permissions. Stop the app before moving aside a leftover temporary
  file. Keep the original media and `sync-state.db` intact.
- A `/run/user/<uid>/doc/<id>/...` path is the normal Documents portal access path.
  Do not manually replace it in the configuration with the host path: that path
  may be inaccessible inside the sandbox. Overview errors show the host path
  when the portal can resolve it; diagnostic logs retain the actual access path.

Before requesting originals, the worker creates and removes a unique,
extensionless probe file in each directory with pending downloads. If that fails,
the affected source scan stops with a folder error; it does not attempt every
download or propagate remote deletions for that incomplete source scan. Other
sources continue. The next pull retries the check, allowing automatic recovery
after permissions are corrected. File-specific failures and permission changes
after the check can still produce individual download errors. The probe does
not certify free disk space or permissions on existing temporary files.

## Upload returns HTTP 413

- File exceeds server/proxy body size limits.
- Increase reverse proxy and Immich upload limits.

## Too many retries / 5xx responses

- Verify Immich health and database/storage availability.
- Increase `retry.baseDelayMilliseconds` and `retry.maxAttempts` if needed.
- Inspect server logs on the Immich side.

## Files are reconsidered after every restart

- Confirm that `sync-state.db` exists beside `config.yaml` and that the current user can read and write both the file and its directory.
- The first start with an empty state database performs a one-time, mode-appropriate bootstrap. Large source trees can take time to enumerate, but this reconciliation runs in the background.
- Later starts still inspect path, size, and UTC modification time to detect changes made while the app was stopped. Unchanged files are not hashed and do not generate Immich API transfers.
- Changing the Immich API URL or API key intentionally selects a new account context. The new context must be bootstrapped even when the watched folders did not change.
- Do not delete `sync-state.db` to clear an individual error: deleting it discards the transfer history for every watched folder and causes a new bootstrap.

## Sync state database cannot be opened

- Stop other tools that may have opened or locked `sync-state.db`, then verify write permission on the configuration directory and available disk space.
- If SQLite reports corruption, the app quarantines the damaged database beside the original using a timestamp and creates a new database. The next start performs a safe bootstrap; the quarantined file is retained for diagnosis or recovery.
- If the database cannot be opened or written, the app stops transfers rather than uploading or downloading without durable state. Check the application logs for the underlying filesystem or SQLite error.
- Windows path: `%LOCALAPPDATA%\Immich Folder Watch\sync-state.db`.
- Linux path: `$XDG_CONFIG_HOME/immich-folder-watch/sync-state.db`, or `~/.config/immich-folder-watch/sync-state.db` when `XDG_CONFIG_HOME` is unset. Flatpak maps this to `~/.var/app/io.github.voltkraft.immich-folder-watch/config/immich-folder-watch/sync-state.db` on the host.

## Verified uploads are not deleted locally

- Confirm `watch.sources[].deleteAfterUpload` is `true` and the source uses `uploadNew` or `uploadAll`. The option is intentionally ignored for `sync` sources.
- Deletion happens only after upload and album assignment succeed, the successful state is persisted, and the current file size and UTC modification time still match. A file changed during or after upload is preserved.
- Files that already existed in an `uploadNew` source but have no verified upload entry in `sync-state.db` are preserved.
- Check write/delete permissions on the watched folder. A deletion failure keeps the verified state and is retried during five-second polling sweeps and after restart without another upload.
- Local deletion is permanent; the file is not moved to the desktop recycle bin or trash. The corresponding Immich asset is not deleted.

## Placeholder text remains visible after collapsing options (Windows)

Versions before 2.9.1 can leave example text such as `private`, `**/cache`, or
`Thumbs.db` floating over unrelated settings after collapsing Advanced options
or scrolling. These are input placeholders, not misplaced configuration values.
Install 2.9.1 or later. Placeholders are now rendered inside their input controls
and follow the same visibility and scroll clipping. No configuration changes are
required.

## Logs

- Console logs include timestamps and structured fields.
- File logs are written to `logging.logDirectory`.
- Configure `logging.logDirectory` as an absolute path.
- The Windows GUI can reset `logging.logDirectory` back to `%LOCALAPPDATA%\Immich Folder Watch\logs` if needed.
