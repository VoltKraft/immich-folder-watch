# Installation on Linux

The desktop app uploads media from local folders or synchronizes folders and
albums with Immich, with a separate sync mode and file filters for each source.

The supported Linux packages are the `x86_64` and `aarch64` Flatpak bundles
attached to future GitHub Releases created by the current workflow. Releases
through `v2.7.0` are not backfilled. The package runs per user and does not
install a system service or need root privileges at runtime.

## Install from GitHub Releases

1. Install Flatpak using your distribution's package manager.
2. Download the bundle matching `flatpak --default-arch` from
   [GitHub Releases](https://github.com/VoltKraft/immich-folder-watch/releases):
   - `x86_64`: `immich-folder-watch-<version>-linux-x64.flatpak`
   - `aarch64`: `immich-folder-watch-<version>-linux-arm64.flatpak`
3. Install and launch the bundle:

```bash
flatpak install --user ./immich-folder-watch-<version>-linux-<architecture>.flatpak
flatpak run io.github.voltkraft.immich-folder-watch
```

Replace `<architecture>` with `x64` or `arm64` according to the mapping above.

The bundle records Flathub as the source for its Freedesktop runtime dependency.
It does not add an update source for Immich Folder Watch itself. Download each
new application version manually and install it with:

```bash
flatpak install --user --or-update ./immich-folder-watch-<version>-linux-<architecture>.flatpak
```

## Flathub (pending initial acceptance)

Release-update automation is prepared, but the app is not advertised as available
on Flathub yet. See the [submission status](../packaging/flatpak/flathub/README.md).
Use the following commands only after a release announces the published listing:

```bash
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub io.github.voltkraft.immich-folder-watch
flatpak update --user io.github.voltkraft.immich-folder-watch
```

For migration from a per-user GitHub bundle, close the app and back up
`~/.var/app/io.github.voltkraft.immich-folder-watch/` first. Remove the old bundle
with `flatpak uninstall --user io.github.voltkraft.immich-folder-watch`, without
`--delete-data`, then install from Flathub using the command above. This keeps
the same app ID and its configuration/sync database. Confirm the installation's
origin and branch with `flatpak list --app --columns=application,origin,branch`
and check folder access and synchronization before resuming unattended use.
Subsequent versions arrive through Flatpak or the desktop software center's
update mechanism.

## First setup

On a fresh setup, the app requests permission to start at login once. Accept
to enable it, or decline and enable it later in **Settings → Start on login**.
Autostart runs hidden when the desktop supports a tray icon; otherwise the
window opens so the application remains reachable.

1. In **Connection**, enter the Immich API URL and key, then select
   **Verify Immich Access**.
2. In **Folders**, select **Add Source** and grant access to a local folder.
   Under **General**, choose an upload mode or bidirectional sync, and review
   album placement and **File filters**. Bidirectional sync also propagates
   deletions; read the [desktop interface guide](user-interface.md#general)
   before selecting it.
3. Use **Settings** for application, transfer, and logging preferences.
4. Select **Save and Apply** to validate and save the configuration and start
   synchronization in the selected modes.

## Sandbox behavior

Folder selection uses the FreeDesktop FileChooser and Documents portals. The
app can access only folders explicitly granted by the user; it does not receive
host-wide or home-directory filesystem access. Use **Choose Folder** in the
source editor to change a folder or renew its grant while keeping the other
source settings.

The package uses X11/XWayland and supports a tray icon through StatusNotifierItem.
KDE Plasma provides a tray host; GNOME requires an AppIndicator extension.
Closing the window hides it while synchronization continues. Reopen it from
the app launcher or the desktop's Background Apps view, and use the in-app Quit
button to stop it completely.

Per-user data is stored under:

- Config: `~/.var/app/io.github.voltkraft.immich-folder-watch/config/immich-folder-watch/config.yaml`
- Sync state: `~/.var/app/io.github.voltkraft.immich-folder-watch/config/immich-folder-watch/sync-state.db`
- File logs: the directory shown under **Settings → Logging**. For fresh settings, this is `immich-folder-watch/logs` below the sandbox's `XDG_STATE_HOME`, falling back to `$HOME/.local/state`. Existing configured directories are retained.

The default journald output can be inspected with:

```bash
journalctl --user -t io.github.voltkraft.immich-folder-watch.desktop
```

See [Flatpak Packaging](../packaging/flatpak/README.md) to build the package
locally.
