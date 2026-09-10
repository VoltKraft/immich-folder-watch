# Flathub preparation validation

Validated on 2026-09-10. Distribution targets are **x86_64 and aarch64**; there
is no 32-bit x86 target. This records preparation and upstream CI, not Flathub
acceptance.
See the [submission and activation guide](../../packaging/flatpak/flathub/README.md)
for current requirements and external prerequisites.

## Executed checks

The final [complete CI run](https://github.com/VoltKraft/immich-folder-watch/actions/runs/34489668378)
passed for commit `ca8cbc78b5dd17f0d8973d1c57e5d9399859dee0`, prepared version
`2.11.1`. Subsequent validation-report edits do not change these package inputs.

| Check | Result |
| --- | --- |
| Python tooling | 83 passed: release/candidate preparation, SDK pins, isolated NuGet generation and license notices. |
| JavaScript updater | 22 passed with mocked GitHub APIs; no live PR created. |
| Actionlint, Bash syntax, manifest resolution, AppStream, desktop entry, diff checks | Passed. The dry parse verifies one Git source, both SDK archives and the sibling feed. |
| Ubuntu Release build/tests | 374 Core and 44 Linux tests passed, including 7 Notification portal regressions. |
| Windows Release solution build/tests | 36 Windows, 366 Core (8 platform skips), and 29 Linux tests (15 native Linux skips) passed. This does not produce an MSI. |
| Exact .NET SDK 10.0.401 restores | 80 x64 and 83 ARM64 packages from fresh caches; merged feed has 83 archives, including both 10.0.12 runtime packs. |
| Native x86_64 Flatpak | Built and passed Flathub repository lint on Freedesktop 26.08. |
| Native aarch64 Flatpak | Built and passed Flathub repository lint on Freedesktop 26.08. |
| Downloaded bundle inspection | Both ELF architectures and 26.08 runtime refs verified; self-contained .NET 10.0.12, no build SDK, notices for 83 archives and the application AGPL license present. No broad filesystem or direct notification-daemon grant. |
| Release preparation baseline | Published v2.11.0 had exactly four nonempty assets and its tag matched commit `ddfbf46f66731302f243909f148d982e88154a52`. The new SDK path requires a new release containing the current packaging. |

Both native exports mirror screenshots and pass repository lint without
diagnostics. The published 25.08 Builder container installs the actual 26.08
runtime/SDK through `--install-deps-from=flathub`; it does not select the app's ABI.
The initial missing 26.08 container-tag issue has been corrected in the workflow.

The delete-after-upload regression now waits for successful completion before
stopping the worker. This avoids cancelling its final persistence write from
inside the test; production code and the deletion/durable-state assertions are
unchanged. Both theory cases passed five consecutive focused .NET 10.0.401
Release runs (10/10), followed by the complete green CI run above.

The final downloaded artifacts and `package-inspection.json` are ignored under
`artifacts/flathub-candidate/`. Bundles were imported only into an isolated
inspection repository; no installed app or user configuration was changed.

| Bundle | SHA-256 |
| --- | --- |
| x86_64 | `95edbfc455aa4098596da73fac9c22569de1a2b81019d312da277907af40305c` |
| aarch64 | `212065cec3400bf90a8bc51ae85f9e36acc1d7e810dcb145c99bbabab2ef28dc` |

At verification time, `FLATHUB_TOKEN`, `FLATHUB_AUTOMATION_ENABLED` and
`FLATHUB_AUTOMERGE_ENABLED` were absent. No `v2.11.1` tag or release was created.

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

- Both native architecture builds are required in CI. A successful package build
  does not prove visible desktop behavior on either target; use the acceptance
  checklist above.
- The actual Flathub update/merge/publication path has not run remotely. Token
  configuration, initial acceptance and Flathub automerge approval remain
  external setup steps. Automated update tests use mocked GitHub APIs.
- Native desktop smoke tests have not been performed. Notification protocol
  tests verify portal submission but cannot prove popup presentation.
- No application library or font dependency was added. The pinned Microsoft
  .NET SDK is a build-only input; its matching runtime is published self-contained.
