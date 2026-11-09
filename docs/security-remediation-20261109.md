# Security Cloud remediation (2026-11-09)

## Scope and evidence

Baseline: `26a0de519ee4f7eae2e556b8da7726539d578594` (`origin/main`, fetched
2026-11-09). One branch: `security/remediate-all-findings`; one consolidated PR
will target `main`. No merge, product release, live Immich access or scanner
suppression is authorized by this work.

The completed original scan is
`wfr_1cb38532afa4dc13e4acdc43f5953f4ebd3b4308486bbadb640050a3194de7fb`,
output `wfo_34ec985cfa7f5ea897a7b584686027d043129b64bf61aa2f9aa4619dace87016`,
target `3d41ef56b524b7acfa11559859fc0c7dab0daa73`, completed 2026-10-03.
Exact scan queries and an unfiltered all-workspace query independently returned
14 findings for repository `github-1152889808` (11 medium, 3 low), all `new`,
with no further cursor. Direct repository-filtered queries unexpectedly returned
zero and were not relied on. Every complete finding was read; none had a saved
patch. No duplicate, resolved, irrelevant or false-positive finding was excluded.
The two download-file findings share one implementation but retain distinct IDs.

## Finding dispositions

These are code-review dispositions, not a claim that Security Cloud has closed
or rescanned them. Final combined validation remains in progress.

| Finding ID | Severity | Component | Remediation | Disposition |
| --- | --- | --- | --- | --- |
| `csf_204d80f4dba65ad2200a0f52` | Medium | Download staging | Unpredictable same-directory staging with exclusive creation; cleanup only the created staging path. | Implemented; targeted tests pass |
| `csf_e072282d3540054e0caa735a` | Medium | Publication actions | Full verified commit SHAs; multiarchitecture build-image digest. | Implemented; workflow tests/review pass |
| `csf_77f3e84ec9b70e5aff765235` | Medium | Watch-root filesystem access | Reject linked entries/components and skip recursive reparse points; recheck upload/download/delete boundaries. | **Partially fixed; concurrent directory replacement remains open** |
| `csf_c793af7c8b73e70cd9cef253` | Medium | Linux secret configuration | Owner-validated private directories, descriptor-relative exclusive 0600 temporary write and atomic replacement. | Implemented; targeted tests pass |
| `csf_3d1deaf494d68bcd8705352c` | Medium | Remote album mutation | Record creation-returned IDs scoped to account/source; refuse pre-existing adoption; mutate by ID; revoke old-path/restart authority. | Implemented; targeted tests pass |
| `csf_740910544257761f129c14fc` | Medium | Download finalization | Atomic no-overwrite move; preserve destinations that appear during transfer. | Implemented; targeted tests pass |
| `csf_22bdb9836b247cce7ea03578` | Medium | WinGet dispatcher | Pass tag as environment data; validate stable version syntax before output/checkout. | Implemented; executable PowerShell tests pass |
| `csf_88aa96fa9a7f83ae24cfc275` | Medium | Remote inventory | Reject pagination/aggregate limits, malformed entries and contradictory continuation instead of reporting a complete inventory. | Implemented; targeted tests pass |
| `csf_ab63fa83a1bc6518321098e3` | Medium | HTTP/realtime transport | HTTPS by default with user-approved explicit insecure HTTP exception; reject redirects. | Implemented; realtime adapter validation pending |
| `csf_7872ec7777b99b8829e90b22` | Medium | WinGet executable | Pin v1.12.13.0 and verify independently checked upstream SHA-256 before token-bearing execution. | Implemented; executable PowerShell tests pass |
| `csf_84f52d35e0746ff5aca7f195` | Medium | Release credentials | Read-only build jobs, no persisted checkout credentials, isolated publication/dispatch write permissions. | Implemented; workflow tests/review pass |
| `csf_9d99342d709dbfe0f2367899` | Low | API response buffering | Headers-only requests and bounded decompressed metadata/error reads; cumulative search limits. Realtime transport also bounded. | Implemented; realtime adapter validation pending |
| `csf_0c8e7f62652e1f88aecb3ab2` | Low | Linux single instance | Verified private per-user fallback instead of predictable shared `/tmp`; primary-only socket cleanup. | Implemented; targeted tests pass |
| `csf_3c832cee2a5242ec46db86c9` | Low | Download resources | Per-asset byte ceiling, free-space reserve, inactivity/overall deadlines and failure cleanup. | Implemented; targeted tests pass |

## Compatibility and limits

- HTTPS is now required by default. The user explicitly approved this change and
  the `immich.allowInsecureHttp: true` migration exception. See
  [configuration](configuration.md). An explicit exception intentionally sends
  credentials and media without TLS; it is not equivalent to HTTPS protection.
- Album authority is recorded in an additive SQLite table; old entries are never
  adopted. Because the cross-platform code cannot prove directory identity after
  offline replacement, worker startup revokes earlier mutation authority. Existing
  albums remain readable/uploadable; rename/delete them in Immich. A failed local
  rename also revokes authority rather than allowing a recreated old path to
  inherit it. No destructive database migration is performed.
- The watch-path mitigation does **not** close the race between checking a pathname
  and opening/deleting it. Full remediation needs platform handle-relative no-follow
  reads/deletes anchored to an authorized root, including Windows reparse-point
  handling and Linux portal compatibility, plus adversarial race regression tests.
  Shared folders writable by untrusted principals remain outside a safe trust
  boundary. This finding must remain open; the PR must remain a draft.
- Default transfer ceilings: 16 MiB per REST metadata response, 64 KiB diagnostic
  prefix, 500 search pages / 125,000 entries / 128 MiB aggregate metadata, 100 GiB
  per download, 1 GiB free-space reserve, 60-second inactivity and 6-hour overall
  download deadline. Limits fail closed and can reject unusually large legitimate
  libraries/media. They are constructor settings, not YAML/GUI controls.
- Free-space checks cannot reserve blocks against unrelated concurrent writers.
  An abrupt process kill can leave a bounded partial file; no persistent per-cycle
  quota or automatic stale-partial cleanup is implemented. Normal error/cancellation
  paths remove staging files. No live storage-pressure test is claimed.
- Native Linux filesystem behavior was exercised on x86_64. ARM64 constants and
  ABI were checked against upstream headers but require actual ARM64 runtime/CI
  evidence. Windows/UNC behavior requires Windows tests; local Linux tests do not
  establish it. No visible UI layout changed.

## Dependencies and provenance

No application package was added or upgraded. Existing Actions were pinned to
verified upstream commits and their MIT licenses checked. The existing Flatpak
builder image is pinned to an OCI index with both amd64 and arm64. WinGet's
previous moving binary is replaced by Microsoft's MIT-licensed fixed release;
its published digest was independently compared with downloaded bytes. See the
[WinGet guide](../packaging/winget/README.md) and
[Flathub guide](../packaging/flatpak/flathub/README.md) for update procedures.
The repository remains AGPL-3.0-only, product version `2.11.3` is unchanged, and
changes remain Unreleased (Keep a Changelog 1.1.0 / Semantic Versioning 2.0.0).

## Validation and follow-up

Targeted regression tests and independent reviews have run during implementation;
[status](status.md) records final combined checks and revision. Independent review
found stale folder authority and the default SocketIO redirect/buffering gap;
these were addressed before handoff. Realtime adapter review is still pending.

The rescan API exposes repository/environment and model/reasoning selection but
no documented branch/commit selector. Branch-scan capability is being checked;
no scan of unchanged `main` will be claimed as validation of the PR.
