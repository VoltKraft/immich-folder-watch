# Flathub preparation validation

Validated on 2026-09-10. Distribution targets are **x86_64 and aarch64**; there
is no 32-bit x86 target. This records local preparation, not Flathub acceptance.
See the [submission and activation guide](../../packaging/flatpak/flathub/README.md)
for current requirements and external prerequisites.

## Executed checks

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tools/tests -p 'test_*.py'` | 63 passed, including release/candidate preparation and license-notice regressions. |
| `node tools/tests/test_update_flathub_pr.cjs` | 18 passed with mocked GitHub APIs; no live PR created. |
| Actionlint on CI, Release, Flathub and native validation workflows | Passed. |
| Bash syntax, YAML/JSON parsing, AppStream, desktop entry, `git diff --check` | Passed. |
| `.NET` Linux app build, Debug | Passed with zero warnings/errors. |
| `.NET` Core tests, Debug | 374 passed. |
| `.NET` Linux tests, Debug | 44 passed, including 7 Notification portal regressions. |
| Offline license/notice installation | All 83 archives accepted; 67 archive-provided files verified byte-for-byte plus 16 immutable upstream supplements. |
| Real published `v2.11.0` metadata and tag | Verified four nonempty release assets and commit `ddfbf46f66731302f243909f148d982e88154a52`. |
| NuGet generation from an isolated clean release checkout | 80 x64 entries and 81 ARM64 entries; deterministic merged feed contains 83 entries. |
| Official Builder 1.4.9, x86_64 offline build | Passed from the generated three-file package using the combined feed. |
| Stable export with screenshot mirroring and full compose URL policy | Passed, including the `screenshots/x86_64` OSTree ref. |
| Flathub repository lint on that export | No errors; warning that Freedesktop 26.08 is available. |

The export was built with `--default-branch=stable`,
`--mirror-screenshots-url=https://dl.flathub.org/media`, and
`--compose-url-policy=full`. An initial run without mirroring failed the
screenshot checks; the final workflow and documented command include these
options. The app was not installed over the user's existing installation.

Generated files and logs remain ignored under `artifacts/flathub-validation/`.
The test used the released revision's original metadata; subsequent upstream
screenshot fixes require a new release to appear in a prepared package.

## Candidate desktop acceptance

After downloading the matching candidate bundle from a successful CI run, close
the currently running app before testing. A Flatpak branch does not isolate
the app's user data. Use a dedicated test configuration and sample folders:

```bash
flatpak install --user ./flatpak-candidate-<commit>-<architecture>.flatpak
flatpak run \
  --env=XDG_CONFIG_HOME=/var/config/flathub-test \
  --env=XDG_STATE_HOME=/var/data/flathub-test/state \
  io.github.voltkraft.immich-folder-watch//test
```

Use `x86_64` or `aarch64` for `<architecture>`. Decline the initial autostart
request during isolated testing: portal/autostart permissions belong to the
application ID and are shared between branches. Configure only a temporary
Immich test album and sample local files. Do not enable local cleanup while
checking basic upload/folder access.

1. Verify the English/German interface, folder chooser, granted folder access,
   tray open/restart/quit, one upload and restart persistence on each available
   target desktop. Check that the normal installation's configuration was not
   reused. Bidirectional sync should be tested only with disposable data.
2. Verify the real desktop presents a portal notification from the test sandbox:

   ```bash
   flatpak run --command=gdbus io.github.voltkraft.immich-folder-watch//test call \
     --session --dest org.freedesktop.portal.Desktop \
     --object-path /org/freedesktop/portal/desktop \
     --method org.freedesktop.portal.Notification.AddNotification flathub-smoke \
     "{'title': <'Immich Folder Watch'>, 'body': <'Portal smoke test'>, 'priority': <'normal'>}"
   ```

   This tests desktop presentation; the automated tests separately verify the
   application's exact payload. A successful D-Bus reply alone does not prove
   the popup was shown. Desktop notification settings/Do Not Disturb may hide it.
3. Check permissions with
   `flatpak info --show-permissions io.github.voltkraft.immich-folder-watch//test`:
   there must be no direct `org.freedesktop.Notifications` talk rule and no broad
   filesystem grant. The tray watcher permission remains.
4. Test autostart/login behavior when ready to use the package with a backed-up
   real configuration, since the portal registration is shared across branches.
5. Close the candidate, then remove only its test branch with
   `flatpak uninstall --user io.github.voltkraft.immich-folder-watch//test`.
   Do not use `--delete-data`, which affects the shared application data.

Native Linux window captures with synthetic data are an optional Flathub listing
quality improvement; they are not needed to prove the notification bus protocol.

## Remaining validation boundaries

- Native ARM64 packaging is configured as a required workflow job but was not
  executed on this x86_64 host. ARM64 dependency generation alone is not proof
  of a successful native build or launch.
- The new GitHub workflow and the actual Flathub update/merge/publication path
  have not run remotely. Token configuration, initial acceptance and Flathub
  automerge approval remain external setup steps.
- Runtime 26.08/.NET extension compatibility remains an external prerequisite
  identified in the submission guide. The notification portal migration is
  implemented; its visible presentation is part of the desktop checks above. The linter's
  runtime warning does not constitute an exception approval.
- Windows build/tests and native desktop smoke tests were not repeated for
  these packaging/tooling changes. No application dependencies were added.
