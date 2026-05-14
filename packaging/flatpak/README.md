# Flatpak Packaging

`immich-folder-watch` ships to Linux desktops as a Flatpak on **Flathub**.
The app builds against the freedesktop runtime 24.08 + the .NET 10 SDK
extension and installs the Avalonia head as a self-contained `linux-x64`
publish.

App ID: `io.github.voltkraft.ImmichFolderWatch`

## Manifest

There is one Flatpak manifest, the Flathub one:

- `flathub/io.github.voltkraft.ImmichFolderWatch.yml` — the source of
  truth. Its source is `type: git` pinned to a release tag + commit.
  This is the file that lives in the per-app
  `flathub/io.github.voltkraft.ImmichFolderWatch` repo, which **Flathub
  builds on its own infrastructure**.

We do **not** build a `.flatpak` bundle in CI — Flathub does the build.
See [`flathub/README.md`](flathub/README.md) for the submission and
continuous-publishing flow.

## Local build

Prerequisites on the dev machine (Fedora shown; Debian/Ubuntu in parens):

```bash
sudo dnf install flatpak flatpak-builder    # apt install flatpak flatpak-builder
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub \
  org.freedesktop.Platform//24.08 \
  org.freedesktop.Sdk//24.08 \
  org.freedesktop.Sdk.Extension.dotnet10//24.08
```

Then, from the repo root:

```bash
# 1) Pre-generate the offline NuGet feed. Flathub forbids network access
#    during the build, so flatpak-builder hands dotnet a frozen package
#    list instead of running `dotnet restore`. Re-run this whenever the
#    NuGet dependency graph changes — most often an Avalonia or .NET
#    package version bump in src/ImmichFolderWatch.App.Linux/*.csproj.
#    A stale feed silently re-installs the OLD packages; when in doubt,
#    regenerate. The script reads the csproj graph from your working
#    tree, so make sure it matches the tag the manifest is pinned to.
./tools/generate-nuget-sources.sh
#    -> writes packaging/flatpak/flathub/nuget-sources.json

# 2) Build + install into the user Flatpak repo.
flatpak-builder --user --install --force-clean \
    packaging/flatpak/build-dir \
    packaging/flatpak/flathub/io.github.voltkraft.ImmichFolderWatch.yml

# 3) Run it (from a terminal so log output is visible).
flatpak run io.github.voltkraft.ImmichFolderWatch
```

Because the manifest source is `type: git` pinned to a release tag,
step 2 builds **exactly the tagged release** — which is also how you
verify a release before submitting it to Flathub.

### Iterating on local (un-pushed) changes

To build your working tree instead of a pushed tag, temporarily replace
the `type: git` source block in
`flathub/io.github.voltkraft.ImmichFolderWatch.yml` with a local-dir
source, then build as above:

```yaml
    sources:
      - type: dir
        path: ../../..
      - nuget-sources.json
```

Revert that change before committing — the committed manifest must stay
`type: git` for Flathub.

`packaging/flatpak/build-dir/`, `packaging/flatpak/.flatpak-builder/`,
`packaging/flatpak/repo/`, `.flatpak-builder/` and
`packaging/flatpak/flathub/nuget-sources.json` are gitignored — they are
regenerated on every build.

> **If a previous build is misbehaving in unexpected ways**, nuke the
> caches and start fresh — flatpak-builder happily reuses partial state,
> so a stale offline feed or an incremental cache hit can hide a real
> change:
>
> ```bash
> rm -rf .flatpak-builder packaging/flatpak/build-dir \
>        packaging/flatpak/.flatpak-builder packaging/flatpak/repo
> rm -f packaging/flatpak/flathub/nuget-sources.json
> ./tools/generate-nuget-sources.sh
> flatpak-builder --user --install --force-clean \
>     packaging/flatpak/build-dir \
>     packaging/flatpak/flathub/io.github.voltkraft.ImmichFolderWatch.yml
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
| `--own-name=org.kde.*` | Lets the SNI client claim its own `org.kde.StatusNotifierItem-<pid>-<id>` bus name so the Watcher can call back for icon / menu / activate; without this Avalonia's tray registration faults with ServiceUnknown. xdg-dbus-proxy only honours subtree wildcards (`.*` after a full segment), so we have to grant the whole `org.kde.*` namespace — the narrowest pattern that actually matches the runtime-suffixed SNI name. |
| `--talk-name=org.freedesktop.portal.Desktop` | FileChooser, Settings, Notification portals |
| `--talk-name=org.freedesktop.portal.Documents` | Resolve doc-portal handles returned by the FileChooser portal; without it Avalonia's `TryGetLocalPath()` blocks on a D-Bus call the proxy refuses, freezing the UI thread |
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
section from `CHANGELOG.md` and emits an AppStream `<release>` block into
`io.github.voltkraft.ImmichFolderWatch.metainfo.xml`, filtering out items
tagged `(Windows)` so the Linux-facing metadata only documents what Linux
users will see. Run it before tagging a release:

```bash
python3 tools/update-appstream.py 2.5.1
```

## Flathub submission

The Flathub manifest under `flathub/` already uses `type: git` with a
pinned tag/commit and a sibling `nuget-sources.json`.
[`flathub/README.md`](flathub/README.md) covers the pre-submission
checklist, the `flathub/flathub` pull request, and the continuous
publishing flow.
