# Troubleshooting

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

## Logs

- Console logs include timestamps and structured fields.
- File logs are written to `logging.logDirectory`.
- Configure `logging.logDirectory` as an absolute path.
- The Windows GUI can reset `logging.logDirectory` back to `%LOCALAPPDATA%\Immich Folder Watch\logs` if needed.
