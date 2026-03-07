# Troubleshooting

## Daemon exits at startup

- Check `immich.serverApiUrl` ends with `/api`.
- Check `immich.apiKey` value is valid.
- Verify Immich server is reachable from this machine.

## Files are detected but not uploaded

- Confirm extension is listed in `watch.extensions`.
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
- If `logging.logDirectory` is relative, it is resolved relative to the directory that contains `config.yaml`.
