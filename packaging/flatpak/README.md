# Flatpak Packaging

Builds a Flatpak of `immich-folder-watch` for Linux desktops.
The manifest pins the freedesktop runtime + .NET 10 SDK extension and
installs the Avalonia head as a self-contained `linux-x64` publish.

App ID: `io.github.voltkraft.ImmichFolderWatch`

## Local build

Prerequisites on the dev machine:

```bash
sudo dnf install flatpak flatpak-builder           # Fedora
# or: sudo apt install flatpak flatpak-builder     # Debian/Ubuntu
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub \
  org.freedesktop.Platform//24.08 \
  org.freedesktop.Sdk//24.08 \
  org.freedesktop.Sdk.Extension.dotnet10//24.08
```

Then, from the repo root:

```bash
# 1) Pre-generate the offline NuGet feed (Flathub forbids network in-build)
./tools/generate-nuget-sources.sh

# 2) Build + install into the user Flatpak repo
flatpak-builder --user --install --force-clean \
    packaging/flatpak/build-dir \
    packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.yaml

# 3) Run it
flatpak run io.github.voltkraft.ImmichFolderWatch
```

`packaging/flatpak/build-dir/`, `packaging/flatpak/.flatpak-builder/`,
`packaging/flatpak/nuget-sources.json` and `packaging/flatpak/repo/` are
gitignored — they are regenerated on every build.

## Sandbox permissions

The manifest declares only the portals the app actually needs:

| `finish-args` | What it enables |
|---|---|
| `--share=ipc` + `--socket=wayland` + `--socket=x11` | Display server access (Avalonia 11.2.x's `UsePlatformDetect()` always uses X11/XWayland; Wayland socket reserved for the eventual native backend) |
| `--share=network` | Talk to the Immich server (HTTP + Socket.IO) |
| `--device=dri` | GPU compositor for Avalonia |
| `--talk-name=org.freedesktop.Notifications` | Toasts |
| `--talk-name=org.kde.StatusNotifierWatcher` | Tray on KDE Plasma + AppIndicator-extended GNOME |
| `--talk-name=org.freedesktop.portal.Desktop` | FileChooser, Settings, Notification portals |
| `--talk-name=org.freedesktop.portal.Background` | Autostart consent + run-in-background |
| `--filesystem=xdg-pictures:ro` + `--filesystem=xdg-videos:ro` | Picker preview only — actual watch I/O goes through doc-portal handles |

Notably **not** granted: `--filesystem=host`, `flatpak-spawn --host`,
`--talk-name=org.freedesktop.systemd1`, raw `--socket=session-bus`.

Verify at runtime with:

```bash
flatpak permissions io.github.voltkraft.ImmichFolderWatch
flatpak info -M io.github.voltkraft.ImmichFolderWatch
```

## Branding assets

`packaging/flatpak/icons/` holds the committed icons that get installed
into `/app/share/icons/hicolor/`:

- `scalable/apps/io.github.voltkraft.ImmichFolderWatch.svg` — copy of `assets/branding/logo.svg`
- `512x512/apps/io.github.voltkraft.ImmichFolderWatch.png` — 512px raster fallback

Both are produced by `tools/BrandAssetGen` from `assets/branding/logo.svg`;
the artefacts under `artifacts/branding/flatpak/` are intermediate. Regenerate
after a logo change:

```bash
~/.dotnet/dotnet run --project tools/BrandAssetGen --configuration Release -- \
    --project-root "$(pwd)"
cp assets/branding/logo.svg \
   packaging/flatpak/icons/scalable/apps/io.github.voltkraft.ImmichFolderWatch.svg
cp artifacts/branding/flatpak/io.github.voltkraft.ImmichFolderWatch.png \
   packaging/flatpak/icons/512x512/apps/io.github.voltkraft.ImmichFolderWatch.png
```

## Release-time AppStream block

`tools/update-appstream.py <version>` reads the matching `## [<version>]`
section from `CHANGELOG.md` and emits an AppStream `<release>` block,
filtering out items tagged `(Windows)` so the Linux-facing metadata only
documents what Linux users will see. Phase 5 wires this into the release
workflow; for local one-offs:

```bash
python3 tools/update-appstream.py 2.5.0
```

## Flathub submission

Phase 4 ships a manifest that uses `type: dir` for fast iteration. For the
Flathub submission (Phase 7) the source flips to `type: git` + a pinned
`tag: vX.Y.Z`. Until then, distribution is via single-file `.flatpak`
bundles attached to GitHub Releases (Phase 5 CI lane).
