# Linux Smoke Tests — Pre-Flathub QA

This is the manual checklist that gates the Flathub submission. Phases 0–5 brought the
Flatpak build to "compiles + packages cleanly + CI green"; Phase 6
proves it actually works on real desktops. Run **every** test here on
**both** target environments before tagging the release and submitting to
Flathub.

**High-severity failures block Flathub submission.** Medium-severity failures are
recorded but do not block.

## 1. Target environments

| Env | OS | Session | How to obtain |
|---|---|---|---|
| **GNOME** | Fedora 41+ Workstation | GNOME 46 on Wayland | Primary dev host (already installed) |
| **KDE** | Fedora 41+ KDE Spin | Plasma 6 on Wayland | Boot from Fedora KDE Spin live USB, or install the `@kde-desktop-environment` group beside GNOME and pick "Plasma" at the SDDM login |

If KDE access is impractical, document that and treat KDE-specific
results as "deferred to follow-up release". Don't fake them.

## 2. Prerequisites

Once, before starting:

1. **Immich server** reachable via HTTPS (or HTTP on a trusted LAN).
   Note the URL and an API key with `asset.upload` and
   `asset.download` permissions. The API key for these tests should
   belong to a throwaway/test account, not the user's main account —
   sync-mode tests will create + rename albums.

2. **Test media set.** Under `~/qa-watch/`:
   ```bash
   mkdir -p ~/qa-watch/{sourceA,sourceB,bidir}
   # 5 small JPGs to sourceA — golden path
   for i in 1 2 3 4 5; do
     convert -size 800x600 xc:skyblue -gravity Center \
       -annotate 0 "QA-A-$i" ~/qa-watch/sourceA/qa-a-$i.jpg
   done
   # Same for sourceB and bidir, with distinct labels
   ```
   (`convert` is from ImageMagick; substitute with any other JPG
   generator if needed.)

3. **Sandbox-config sanity:**
   ```bash
   flatpak --user uninstall io.github.voltkraft.immich-folder-watch 2>/dev/null
   rm -rf ~/.var/app/io.github.voltkraft.immich-folder-watch
   ```
   Each environment should start from zero so the "fresh install"
   path is genuinely fresh.

## 3. How to read the result columns

Each test has:
- **ID** — `SMK-NN` for the matrix
- **Severity** — `H` (blocks v1.0) or `M` (tracked, non-blocking)
- **Setup** — environment-specific preconditions (omitted when none)
- **Steps** — numbered actions
- **Expected** — observed outcome that counts as pass
- **Notes** — pitfalls, log lines to look for, or known gaps

Record outcome inline as `[PASS]`, `[FAIL: <one-line reason>]`, or
`[SKIP: <reason>]`. The matrix at the end of this doc summarises.

## 4. Tests

### A. Install + sandbox hygiene

#### SMK-01 — Fresh `flatpak-builder --user --install` succeeds  `H`

Steps:
1. From the repo root: `tools/generate-nuget-sources.sh` (regenerates
   the offline NuGet feed; writes
   `packaging/flatpak/flathub/nuget-sources.json`).
2. `flatpak-builder --user --install --force-clean
   packaging/flatpak/build-dir
   packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml`

Expected: build finishes without error, `flatpak list --user` lists
`io.github.voltkraft.immich-folder-watch`. The bundle size should be in
the 80–200 MB range.

Notes: the manifest source is `type: git` pinned to a release tag, so
this builds the tagged release — to smoke-test un-pushed changes, use
the local-iteration note in `packaging/flatpak/README.md`. If the NuGet
feed is stale, the build can mysteriously revert to old package
versions — regenerate it (step 1).

#### SMK-02 — Sandbox permissions match the manifest  `H`

Steps:
1. `flatpak info -m io.github.voltkraft.immich-folder-watch | sed -n
   '/^\[Context\]/,/^$/p; /^\[Session Bus Policy\]/,/^$/p'`

Expected: output is the INI translation of the manifest's
`finish-args:` block —

```
[Context]
shared=ipc;network;
sockets=x11;
devices=dri;

[Session Bus Policy]
org.freedesktop.Notifications=talk
```

(The order of bus-policy lines is not deterministic.)

Forbidden lines (must NOT appear): `host` in `filesystems=`,
`session-bus` in `sockets=`, `org.freedesktop.systemd1=talk`,
any `org.kde.*` StatusNotifierItem policy, anything `=own`, `wayland` in
`sockets=`, `xdg-pictures`, `xdg-videos`, `home`, or any other static
filesystem grant beyond Flatpak's implicit app-private XDG dirs.

#### SMK-03 — Cold launch from a terminal  `H`

Steps:
1. `flatpak run io.github.voltkraft.immich-folder-watch 2>&1 | tee /tmp/cold-launch.log`

Expected: main window appears within ~3 s; the log shows portal
probes and "App ready" but no exception. Closing the window leaves
the process running (or exits, depending on tray availability — see
SMK-13/14).

Notes: any unhandled-exception line, especially `TypeLoadException` or
`ServiceUnknown` D-Bus errors, is a fail. `phase4_lessons.md` rules
2–4 cover the historical landmines.

#### SMK-04 — Launch from the application menu / GNOME Activities  `H`

Steps:
1. Open Activities (GNOME) or KRunner / Plasma launcher (KDE).
2. Type "Immich Folder Watch", click the result.

Expected: same window appears. The icon used in the launcher matches
the bundled Flatpak icon (not a generic gear).

#### SMK-05 — Second launch hands off to the running instance  `H`

Steps:
1. With the app already running, run `flatpak run
   io.github.voltkraft.immich-folder-watch` from a second terminal.
2. Inspect `~/.var/app/io.github.voltkraft.immich-folder-watch/.local/state/immich-folder-watch/logs/`
   for a "second instance handed off" line.

Expected: the second invocation exits within ~1 s without opening a
new window; the existing window is brought to front (raised /
focused). The UDS at `$XDG_RUNTIME_DIR/immich-folder-watch.sock` is
the carrier — verify `ls $XDG_RUNTIME_DIR/immich-folder-watch.sock`.

### B. First-run + portal-driven config

#### SMK-06 — Folder picker opens via FileChooser portal  `H`

Steps:
1. Click "+ Add watched folder" / equivalent in Settings.
2. In the resulting picker, navigate to `~/qa-watch/sourceA` and
   confirm.

Expected: the picker is the GTK/KDE *portal* picker (not Avalonia's
fallback ad-hoc one). After confirmation, the folder appears in the
Watch list with a path like `/run/user/1000/doc/<id>/sourceA`.

Notes: if the picker hangs, check the log for
`org.freedesktop.portal.Documents` errors — see
`phase4_lessons.md` rule (FileChooser portal Documents talk-name).

#### SMK-07 — Picker rejects truly inaccessible paths gracefully  `M`

Steps:
1. Try to pick `/root/` via the picker (Ctrl-L → type `/root/` →
   Enter). Choose `/root/` itself if listed, or any path inside.

Expected: the picker either disallows the navigation (portal-side
ACL: directory not readable to the user) or returns no doc handle.
App stays responsive; no crash.

Notes: do NOT use `/etc/` as the test target — most of /etc is
user-readable so the portal correctly grants a doc handle, and the
app then accepts a path that's nonsensical as a watch source. That
is a real but non-blocking gap (app should validate system paths
itself); track it as a follow-up rather than calling SMK-07 a fail.

#### SMK-08 — First-time API key + URL save without freezing  `H`

Steps:
1. In Settings, paste the Immich URL and API key.
2. Click "Test connection".
3. Save.

Expected: the connection-test status pill turns green within ~5 s
(or red if URL/key wrong, with a clear localized message). Save
persists; restart the app and confirm the values are still there
(masked API key).

#### SMK-09 — Windows-style config path is rejected with a clear error  `H`

Steps:
1. Quit the app.
2. Edit `~/.var/app/io.github.voltkraft.immich-folder-watch/config/immich-folder-watch/config.yaml`,
   change a watch source path to `C:\Users\foo\Pictures`.
3. Launch the app.

Expected: an in-window banner (or modal) explaining that
Windows-style paths are unsupported on Linux, with a "Re-pick folder"
action. The app does NOT silently auto-migrate.

### C. Watch + upload — golden path

#### SMK-10 — Drop a JPG into a watched folder, see it uploaded  `H`

Setup: a watched folder pointing at `~/qa-watch/sourceA` (configured
in SMK-06), connection green from SMK-08.

Steps:
1. Copy a fresh JPG into `~/qa-watch/sourceA`:
   ```bash
   cp ~/qa-watch/bidir/qa-bidir-1.jpg ~/qa-watch/sourceA/new1.jpg
   ```
2. Wait 5–10 s.
3. In Immich web UI, look for the asset.

Expected: the asset appears in Immich; the Recent Activity panel /
status pill shows "Uploaded 1 file" or equivalent; tray/notification
fires (see SMK-13/14/15).

#### SMK-11 — Move (instead of copy) a JPG into a watched folder  `H`

Steps: same as SMK-10 but with `mv`.

Expected: same end state. (`FileSystemWatcher`'s rename event is the
historical regression risk.)

#### SMK-12 — Upload-batch behaviour: 25 files at once  `M`

Steps:
1. `cp ~/qa-watch/sourceB/*.jpg ~/qa-watch/sourceA/` 25 times via a
   loop (use `bench/`-style scratch files).
2. Watch the status panel and Immich.

Expected: uploads happen in batches per the
`maxBatchSize` config (default 25) without overwhelming the server;
no duplicates appear in Immich; final count matches.

### D. Sync modes + album rename

#### SMK-13 — `upload` mode: only new files go up  `H`

Setup: watched folder in `upload` mode (default).

Steps:
1. Place an existing-from-before file in the folder; place a new file.
2. Wait 10 s.

Expected: only the new file is uploaded; previously-uploaded asset
is not re-uploaded (no duplicate in Immich).

#### SMK-14 — `uploadAll` mode: full folder one-shot  `H`

Steps:
1. Switch the folder to `uploadAll` in Settings, save.
2. Confirm prompt.

Expected: every file currently in the folder gets queued; tracked in
status; no duplicate creation if files were already in Immich (server
de-dupes by hash).

#### SMK-15 — `bidirectional` mode + subfolder ↔ album rename  `H`

Setup: watched folder is `~/qa-watch/bidir`, mode `bidirectional`,
linked to album "QA-Bidir".

Steps:
1. With files already in sync, rename the **folder** on disk:
   `mv ~/qa-watch/bidir ~/qa-watch/bidir-renamed`.
2. Stop / restart watcher, or (if hot-reload supported) wait.
3. Check Immich's album list.

Expected: the album in Immich is renamed to match. No assets are
deleted or re-uploaded (additive semantics — local files are never
deleted, server album just gains a new name).

Reverse direction:
4. Rename the album in Immich web UI.
5. Wait for the next watcher tick or restart.

Expected: the local folder either renames (preferred) OR a banner
explains the mismatch with a "Reconcile" button. Specify which.

### E. Notifications + background mode

#### SMK-16 — No toast on success; failure surfaces in UI / log  `M`

Per user preference (2026-05-10): no notification on every upload
completion — that was the original Phase-1 sketch but in production
becomes notification-spam. Only persistent failures should surface
via toast, because those need user attention.

Steps:
1. SMK-10 (drop a file). Confirm NO toast appears on success.
2. Force a failure: temporarily wrong API key OR offline server.
3. Drop another file.

Expected:
- Step 1: silent. Status row + log show the upload, but the
  notification daemon doesn't get a Notify call for the success
  path. Verified by `dbus-monitor --session "interface='org.freedesktop.Notifications'"`
  (no traffic during step 1).
- Step 3: failure-toast surfaces (NOT IMPLEMENTED YET — tracked as
  a follow-up; for now mark as `[NOTE: failure-toast deferred]`).

Notes: INotifier / DBusNotifier infrastructure is wired and the
Flatpak manifest grants `--talk-name=org.freedesktop.Notifications`,
but the FolderWatchWorker's upload-failure path doesn't call
ShowAsync yet. Hooking it up to FlushUploadsAsync's else-branch
("Upload failed for {FilePath}") plus a dedup window (one toast
per asset+error class per minute) is a small follow-up commit.

#### SMK-17 — Flatpak tray-disabled banner  `H`

Setup: any supported Flatpak desktop session.

Steps:
1. Launch app.
2. Confirm the main window shows a banner explaining that tray
   integration is disabled in the current Flathub build.
3. Close the window via the X button; the process remains running.
4. Launch the app again from the desktop launcher or terminal.
5. Confirm the existing instance shows and activates the same window.
6. Use the footer `Quit` button; `pgrep -f immich-folder-watch` returns
   nothing.

Expected: no tray icon is registered and there is no
`StatusNotifierWatcher`/`org.kde.*` D-Bus policy in the installed Flatpak
metadata. The banner keeps the close-to-background behavior discoverable
until a Flatpak-safe tray backend is available.

Notes: Flathub no longer accepts the broad KDE D-Bus own-name grant required
by Avalonia's current SNI backend for new apps, so the first Flathub release
ships without tray support.

#### SMK-18 — Background mode on bare GNOME (no AppIndicator)  `H`

Setup: GNOME 46+ without the AppIndicator and KStatusNotifierItem
Support extension. Confirm with
`gnome-extensions list | grep -i appindicator` returning nothing.

Steps:
1. Launch app.
2. Observe the banner under the header card.
3. Close the window via the X button.
4. Confirm the process keeps running: `pgrep -f immich-folder-watch`.
5. Open GNOME Quick Settings (top-right click) → expand
   "Background Apps" → look for "Immich Folder Watch".
6. Click the launcher icon in Activities again.
7. Use the footer Quit button (or the Background-Apps panel's Quit
   action) to actually exit.

Expected at each step:
- (2) Banner reads roughly "No system tray icon — closing the
  window only hides it; the watcher keeps running in the
  background. Re-open via the app launcher (Activities, dock, or
  GNOME 46+ Quick Settings → Background Apps). Use the Quit
  button to actually exit."
- (3) Window disappears; process stays alive.
- (4) `pgrep` lists the immich-folder-watch process.
- (5) "Background Apps" lists "Immich Folder Watch" with a Quit
  action. First time the window is hidden after a fresh install,
  GNOME may surface a one-time consent dialog from xdg-desktop-
  portal-Background — accept it.
- (6) Window re-appears via the existing single-instance handoff
  (UnixSingleInstanceCoordinator over a Unix socket).
- (7) Process exits cleanly.

Notes: this is the e5bd528 + tray-banner UX. The
BackgroundPortalClient.RequestBackgroundAsync call fires once per
session at the first hide; later hides skip the call.

### F. Theme + i18n

#### SMK-19 — Live light → dark via Settings portal  `H`

Steps:
1. With the app open, switch system theme via GNOME Quick Settings
   (Wayland) or the KDE System Settings → Appearance.

Expected: the app's theme follows within ~1 s without a restart. No
flicker; text/accent colours legible in both.

#### SMK-20 — Live language switch EN ↔ DE  `H`

Steps:
1. Settings → Language → switch.

Expected: every visible string updates immediately; no restart
required. Sync status pills, button labels, and any open
context-menu items refresh too.

#### SMK-21 — OS-language autodetect on first run  `M`

Steps:
1. Set system locale to `de_DE.UTF-8` (or the inverse if already DE).
2. Wipe `~/.var/app/io.github.voltkraft.immich-folder-watch/`.
3. Launch.

Expected: the app starts in the system's language by default; user
can override via Settings.

### G. Autostart consent

#### SMK-22 — Toggle autostart ON triggers Background portal prompt  `H`

Steps:
1. Settings → Autostart → ON.

Expected: a portal dialog appears asking for consent to run in the
background (and to start at login). Granting it persists; the toggle
remains ON across app restarts.

#### SMK-23 — Toggle autostart OFF revokes it  `H`

Steps:
1. With autostart ON, log out and log back in. Confirm the app
   starts automatically. Quit it.
2. Settings → Autostart → OFF.

Expected: log out, log back in. The app does not auto-start. No
zombie `.desktop` autostart file is left behind in
`~/.config/autostart/` (the Background portal is the only mechanism;
no XDG fallback).

### H. Doc-handle persistence + reboot

#### SMK-24 — Picked folders survive an app restart  `H`

Steps:
1. After SMK-06 + SMK-08, fully quit the app.
2. Re-launch.

Expected: the watched folders list is intact; the app continues
watching them without re-prompting the picker.

#### SMK-25 — Picked folders survive a host reboot  `H`

Steps:
1. After SMK-24, `reboot` the host.
2. Log back in, launch the app.

Expected: same as SMK-24. The portal token persisted in
`config.yaml` is re-resolved via `org.freedesktop.portal.Documents.Lookup`
on startup. If a token is invalid, a "Re-pick folder" banner appears
for that source (not a crash).

### I. Inotify limit warnings

#### SMK-26 — Pre-flight warning at >50% of `fs.inotify.max_user_watches`  `M`

Setup:
```bash
sysctl fs.inotify.max_user_watches    # note current value
```

Steps:
1. Configure a watched folder pointing at a directory tree large
   enough to consume >50% of the limit:
   ```bash
   cd /tmp && mkdir -p qa-bigfolder
   for i in $(seq 1 60000); do mkdir -p qa-bigfolder/d$i; done
   ```
2. Add `/tmp/qa-bigfolder` to the watch list.

Expected: a non-blocking banner warns that the inotify limit is being
approached; a tooltip or link explains how to raise
`fs.inotify.max_user_watches` via sysctl.

#### SMK-27 — Hard refusal at ≥95%  `M`

Steps: extend `qa-bigfolder` until >95% of the watch limit is
consumed.

Expected: when the user tries to add another watched folder, the app
refuses with a clear message (does not silently swallow watches).

### J. Cross-device move fallback (`EXDEV`)

#### SMK-28 — Bidirectional move across filesystems falls back to copy+delete  `M`

Setup: a second filesystem is mounted (e.g. an external SSD at
`/run/media/<user>/<label>`). The watch folder's parent is on that
device, the album rename triggers a move that crosses devices.

Steps:
1. Configure a bidirectional watch on a folder on the external device.
2. Trigger an album rename in Immich that would translate to a move
   onto the internal disk.

Expected: the watcher catches the `EXDEV` errno from `Directory.Move`
and falls back to copy+delete. No data loss; final state matches
single-device behaviour.

### K. Logging path + Open Log Folder

#### SMK-29 — Logs land in the sandbox  `H`

Steps:
1. Run the app for a minute with some uploads.
2. `ls "~/.var/app/io.github.voltkraft.immich-folder-watch/data/Immich Folder Watch/logs/"`

Expected: at least one rolling log file present, recent timestamp,
non-empty content. Format matches the file logger from `Core`.

Note: the path uses XDG_DATA_HOME with the WPF-era folder name
"Immich Folder Watch" because `MainWindowViewModel._logDirectory`
seeds itself from `InstallationPaths.GetLogDirectory()` (a constant
shared with WPF) before the Linux MainWindow's `XdgPlatformPaths`
seed branch runs. Functionally fine — sandbox-internal,
`Open log folder` resolves it, deleting it on uninstall is covered
by SMK-33. A future cleanup can route the default through
`IPlatformPaths` to land at the spec-compliant
`.local/state/immich-folder-watch/logs/`.

#### SMK-30 — `Open log folder` button uses xdg-open inside the sandbox  `M`

Steps:
1. Settings → Open log folder.

Expected: the user's default file manager opens, focused on the
sandbox log path. The path may be displayed verbatim (e.g.
`/home/jan/.var/app/.../logs/`); that's fine for v1.

#### SMK-31 — Journald sees the structured stderr stream  `M`

Steps:
1. Open the app, switch `Logging → Target` to `Journald`,
   `Save & Apply` (the AppHost restarts and 3.8.B's per-target
   gating swaps `FileLoggerProvider` for `AddSystemdConsole`).
2. Drop a test file into a watched source so an upload fires.
3. `journalctl --user --since "2 min ago" -t io.github.voltkraft.immich-folder-watch.desktop --no-pager`
   (under Flatpak's portal-launcher the `_SYSLOG_IDENTIFIER` is the
   .desktop filename, not the project's short name — `-t
   immich-folder-watch` returns "No entries").
4. Switch `Logging → Target` back to `File`, `Save & Apply`.

Expected: lines from step 3 carry the `<6>` / `<7>` priority prefix
that the systemd console formatter prepends, severity levels match
the message content (e.g. `<6>` for `info`, `<7>` for `dbug`,
`<4>` for `warn`). Plain `YYYY-MM-DD … info: …` lines from before
the restart should also be visible — those are the previous
`FileLoggerProvider` writes that journald captured via stdout.

### L. Quit + cleanup

#### SMK-32 — Quit via menu / window close releases all resources  `H`

Steps:
1. Quit via File → Quit (or the platform equivalent).
2. `pgrep -af immich-folder-watch` and `ls $XDG_RUNTIME_DIR/immich-folder-watch.sock`.

Expected: no leftover process; the UDS socket is removed (or stale
and cleaned up on next start). No D-Bus name still owned by us
(verify with `busctl --user list --no-pager | grep -i immich` if you
want to be thorough — should be empty).

#### SMK-33 — Sandbox uninstall is clean  `H`

Steps:
1. `flatpak --user uninstall io.github.voltkraft.immich-folder-watch`
2. `ls ~/.var/app/io.github.voltkraft.immich-folder-watch/`

Expected: uninstall succeeds; the data directory remains (Flatpak's
default, intentional — user data is preserved across reinstalls).
Adding `--delete-data` should remove that too.

## 5. Sign-off matrix

Fill in for each environment:

| ID | Title | Severity | GNOME | KDE |
|---|---|---|---|---|
| SMK-01 | flatpak-builder install | H | | |
| SMK-02 | sandbox permissions | H | | |
| SMK-03 | cold launch terminal | H | | |
| SMK-04 | launch from menu | H | | |
| SMK-05 | second-launch handoff | H | | |
| SMK-06 | folder picker portal | H | | |
| SMK-07 | picker permission rejection | M | | |
| SMK-08 | API key save | H | | |
| SMK-09 | Windows-config rejection | H | | |
| SMK-10 | upload golden path | H | | |
| SMK-11 | move into folder | H | | |
| SMK-12 | batch of 25 | M | | |
| SMK-13 | upload mode | H | | |
| SMK-14 | uploadAll mode | H | | |
| SMK-15 | bidirectional + rename | H | | |
| SMK-16 | toast on upload | H | | |
| SMK-17 | tray on KDE | M | n/a | |
| SMK-18 | window-only on GNOME | H | | n/a |
| SMK-19 | theme follow | H | | |
| SMK-20 | language switch | H | | |
| SMK-21 | locale autodetect | M | | |
| SMK-22 | autostart ON consent | H | | |
| SMK-23 | autostart OFF | H | | |
| SMK-24 | doc handles after restart | H | | |
| SMK-25 | doc handles after reboot | H | | |
| SMK-26 | inotify warn >50% | M | | |
| SMK-27 | inotify refuse ≥95% | M | | |
| SMK-28 | EXDEV fallback | M | | |
| SMK-29 | logs in sandbox state | H | | |
| SMK-30 | Open log folder | M | | |
| SMK-31 | journald sees stderr | M | | |
| SMK-32 | quit cleanup | H | | |
| SMK-33 | uninstall clean | H | | |

**v1.0 is shippable when:** every `H` row is `PASS` on **at least
GNOME**, AND every `H` row except SMK-17 is `PASS` on KDE if KDE
testing happened. Outstanding `M` rows go on the Phase-7 follow-up
list, not the blocker list.

## 6. After signing off

1. Bump `Directory.Build.props` via
   `tools/release/bump-version.sh <version>`.
2. Fill in CHANGELOG.md release notes under the new heading.
3. `python3 tools/update-appstream.py <version>` to refresh the
   metainfo `<release>` block.
4. `git commit -m "release: v<version>"` on `main`.
5. Push — `release.yaml` builds the Windows MSI and attaches it to a
   GitHub Release tagged `v<version>`.
6. Linux ships via Flathub — see
   `packaging/flatpak/flathub/README.md` for the submission and
   continuous-publishing flow.
