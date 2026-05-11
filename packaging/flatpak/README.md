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
# 1) Pre-generate the offline NuGet feed (Flathub forbids network during the
#    build, so flatpak-builder hands dotnet a frozen package list).
#    Run this once on the first build, AND every time anything under src/
#    changes its NuGet dependencies — most commonly an Avalonia or .NET
#    package version bump in src/ImmichFolderWatch.App.Linux/*.csproj.
#    A stale nuget-sources.json silently re-installs the OLD packages,
#    which has burned us repeatedly. If in doubt, regenerate.
./tools/generate-nuget-sources.sh

# 2) Create the local source archive consumed by the Flatpak manifest.
#    This uses tracked files from the working tree, so local edits to
#    tracked files are included while ignored build output stays out.
git ls-files -z \
  | tar --create --gzip --file packaging/flatpak/source.tar.gz \
      --null --files-from -

# 3) Resolve the generated NuGet source fragment into a buildable JSON
#    manifest and normalize the local source archive into an explicit
#    read-only build sandbox mount. Directly building the YAML can leave
#    sources unstaged with flatpak-builder versions that reject mixed
#    object/string sources or local archive sources.
flatpak-builder --show-manifest \
    packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.yaml \
    > packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json
python3 tools/normalize-flatpak-manifest-paths.py \
    packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json \
    --manifest-dir packaging/flatpak

# 4) Build + install into the user Flatpak repo
flatpak-builder --user --install --force-clean \
    packaging/flatpak/build-dir \
    packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json

# 5) Run it (from a terminal so log output is visible)
flatpak run io.github.voltkraft.ImmichFolderWatch
```

`packaging/flatpak/build-dir/`, `packaging/flatpak/.flatpak-builder/`,
`packaging/flatpak/nuget-sources.json`, `packaging/flatpak/source.tar.gz`
and `packaging/flatpak/repo/` are gitignored — they are regenerated on
every build.

> **If a previous build is misbehaving in unexpected ways**, nuke the
> caches and start fresh. flatpak-builder happily reuses partial state
> from the last run, so a stale offline feed or an incremental cache hit
> can hide a real change:
>
> ```bash
> rm -f packaging/flatpak/nuget-sources.json packaging/flatpak/source.tar.gz
> rm -rf .flatpak-builder packaging/flatpak/build-dir
> ./tools/generate-nuget-sources.sh
> git ls-files -z \
>   | tar --create --gzip --file packaging/flatpak/source.tar.gz \
>       --null --files-from -
> flatpak-builder --show-manifest \
>     packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.yaml \
>     > packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json
> python3 tools/normalize-flatpak-manifest-paths.py \
>     packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json \
>     --manifest-dir packaging/flatpak
> flatpak-builder --user --install --force-clean \
>     packaging/flatpak/build-dir \
>     packaging/flatpak/io.github.voltkraft.ImmichFolderWatch.resolved.json
> ```

## Sandbox permissions

The manifest declares only the portals the app actually needs:

| `finish-args` | What it enables |
|---|---|
| `--share=ipc` + `--socket=wayland` + `--socket=x11` | Display server access. Avalonia 11.3.x renders over XWayland on Wayland sessions; the `--socket=wayland` line is reserved for the future Wayland-native backend. |
| `--share=network` | Talk to the Immich server (HTTP + Socket.IO) |
| `--device=dri` | GPU compositor for Avalonia |
| `--talk-name=org.freedesktop.Notifications` | Toasts |
| `--talk-name=org.kde.StatusNotifierWatcher` | Tray on KDE Plasma + AppIndicator-extended GNOME |
| `--own-name=org.kde.*` | Lets the SNI client claim its own `org.kde.StatusNotifierItem-<pid>-<id>` bus name so the Watcher can call back for icon / menu / activate; without this Avalonia's tray registration faults with ServiceUnknown. xdg-dbus-proxy only honours subtree wildcards (`.*` after a full segment), so we have to grant the whole `org.kde.*` namespace — the narrowest pattern that actually matches the runtime-suffixed SNI name |
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

The in-repo release manifest uses a local `source.tar.gz` file generated
from `git ls-files` immediately before each build. The resolved manifest
normalization mounts that archive read-only into the build sandbox and
unpacks it there. For Flathub, use the separate manifest under
`packaging/flatpak/flathub/`, which already uses `type: git` plus a pinned
tag/commit and a sibling `nuget-sources.json`.
