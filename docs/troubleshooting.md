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

## Logs

- Console logs include timestamps and structured fields.
- File logs are written to `logging.logDirectory`.
- Configure `logging.logDirectory` as an absolute path.
- The Windows GUI can reset `logging.logDirectory` back to `%LOCALAPPDATA%\Immich Folder Watch\logs` if needed.
