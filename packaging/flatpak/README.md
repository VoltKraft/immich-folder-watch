# Flatpak Packaging

`immich-folder-watch` ships to Linux desktops as a Flatpak on **Flathub**.
The app builds against the freedesktop runtime 25.08 + the .NET 10 SDK
extension and installs the Avalonia head as a self-contained `linux-x64`
publish.

App ID: `io.github.voltkraft.immich-folder-watch`

## Manifest

There is one Flatpak manifest, the Flathub one:

- `flathub/io.github.voltkraft.immich-folder-watch.yml` — the source of
  truth. Its source is `type: git` pinned to a release tag + commit.
  This is the file that lives in the per-app
  `flathub/io.github.voltkraft.immich-folder-watch` repo, which **Flathub
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
  org.freedesktop.Platform//25.08 \
  org.freedesktop.Sdk//25.08 \
  org.freedesktop.Sdk.Extension.dotnet10//25.08
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
    packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml

# 3) Run it (from a terminal so log output is visible).
flatpak run io.github.voltkraft.immich-folder-watch
```

Because the manifest source is `type: git` pinned to a release tag,
step 2 builds **exactly the tagged release** — which is also how you
verify a release before submitting it to Flathub.

### Iterating on local (un-pushed) changes

To build your working tree instead of a pushed tag, temporarily replace
the `type: git` source block in
`flathub/io.github.voltkraft.immich-folder-watch.yml` with a local-dir
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
>     packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml
> ```

## Sandbox permissions

The manifest declares only the portals the app actually needs:

| `finish-args` | What it enables |
|---|---|
| `--share=ipc` + `--socket=x11` | X11/XWayland display access. Avalonia's current Linux backend initializes X11. |
| `--share=network` | Talk to the Immich server (HTTP + Socket.IO) |
| `--device=dri` | GPU compositor for Avalonia |
| `--talk-name=org.freedesktop.Notifications` | Toasts |

Notably **not** granted: `--filesystem=host`, `flatpak-spawn --host`,
`--filesystem=home`, `--filesystem=xdg-pictures`,
`--filesystem=xdg-videos`, `--talk-name=org.freedesktop.systemd1`, raw
`--socket=session-bus`, `--socket=wayland`, or StatusNotifierItem permissions.
Folder access is intentionally portal-based for the first Flathub release. The
current Avalonia tray backend needs a broad KDE D-Bus own-name grant that
Flathub no longer accepts for new apps, so the Flathub build starts in
window-only mode and shows an in-app banner until a Flatpak-safe tray backend
is available.

Verify at runtime with:

```bash
flatpak permissions io.github.voltkraft.immich-folder-watch
flatpak info -M io.github.voltkraft.immich-folder-watch
```

## Branding assets

`packaging/flatpak/icons/` holds the committed icons that get installed
into `/app/share/icons/hicolor/`:

- `scalable/apps/io.github.voltkraft.immich-folder-watch.svg` — copy of `assets/branding/logo.svg`
- `512x512/apps/io.github.voltkraft.immich-folder-watch.png` — 512px raster fallback

Both are produced by `tools/BrandAssetGen` from `assets/branding/logo.svg`;
the artefacts under `artifacts/branding/flatpak/` are intermediate. Regenerate
after a logo change:

```bash
~/.dotnet/dotnet run --project tools/BrandAssetGen --configuration Release -- \
    --project-root "$(pwd)"
cp assets/branding/logo.svg \
   packaging/flatpak/icons/scalable/apps/io.github.voltkraft.immich-folder-watch.svg
cp artifacts/branding/flatpak/io.github.voltkraft.immich-folder-watch.png \
   packaging/flatpak/icons/512x512/apps/io.github.voltkraft.immich-folder-watch.png
```

## Release-time AppStream block

`tools/update-appstream.py <version>` reads the matching `## [<version>]`
section from `CHANGELOG.md` and emits an AppStream `<release>` block into
`io.github.voltkraft.immich-folder-watch.metainfo.xml`, filtering out items
tagged `(Windows)` so the Linux-facing metadata only documents what Linux
users will see. Run it before tagging a release:

```bash
python3 tools/update-appstream.py 2.5.3
```

## Flathub submission

The Flathub manifest under `flathub/` already uses `type: git` with a
pinned tag/commit and a sibling `nuget-sources.json`.
[`flathub/README.md`](flathub/README.md) covers the pre-submission
checklist, the `flathub/flathub` pull request, and the continuous
publishing flow.
