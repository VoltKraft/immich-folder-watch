# Installation on Linux

The supported Linux package is the `x86_64` Flatpak bundle attached to future
GitHub Releases created by the current workflow. Releases through `v2.7.0` are
not backfilled. The package runs per user and does not install a system service
or need root privileges at runtime.

## Install from GitHub Releases

1. Install Flatpak using your distribution's package manager.
2. Download `immich-folder-watch-<version>.flatpak` from
   [GitHub Releases](https://github.com/VoltKraft/immich-folder-watch/releases).
3. Install and launch the bundle:

```bash
flatpak install --user ./immich-folder-watch-<version>.flatpak
flatpak run io.github.voltkraft.immich-folder-watch
```

The bundle records Flathub as the source for its Freedesktop runtime dependency.
It does not add an update source for Immich Folder Watch itself. Download each
new application version manually and install it with:

```bash
flatpak install --user --or-update ./immich-folder-watch-<version>.flatpak
```

The Flathub publication is currently postponed. Do not use
`flatpak install flathub io.github.voltkraft.immich-folder-watch` unless a future
release explicitly announces that the listing is available.

## Sandbox behavior

Folder selection uses the FreeDesktop FileChooser and Documents portals. The
app can access only folders explicitly granted by the user; it does not receive
host-wide or home-directory filesystem access.

The package currently uses X11/XWayland and runs without a system tray icon.
Closing the window hides it while the watcher continues running. Reopen it from
the app launcher or the desktop's Background Apps view, and use the in-app Quit
button to stop it completely.

Per-user data is stored under:

- Config: `~/.var/app/io.github.voltkraft.immich-folder-watch/config/immich-folder-watch/config.yaml`
- Sync state: `~/.var/app/io.github.voltkraft.immich-folder-watch/config/immich-folder-watch/sync-state.db`
- File logs: `~/.var/app/io.github.voltkraft.immich-folder-watch/data/Immich Folder Watch/logs/`

The default journald output can be inspected with:

```bash
journalctl --user -t io.github.voltkraft.immich-folder-watch.desktop
```

See [Flatpak Packaging](../packaging/flatpak/README.md) to build the package
locally.
