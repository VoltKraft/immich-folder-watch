# Flatpak Packaging

`immich-folder-watch` ships to Linux desktops as an `x86_64` Flatpak bundle on
**GitHub Releases**. The app builds against the freedesktop runtime 25.08 + the
.NET 10 SDK extension and installs the Avalonia head as a self-contained
`linux-x64` publish.

App ID: `io.github.voltkraft.immich-folder-watch`

The current workflow adds the bundle to future releases. Existing releases
through `v2.7.0` remain MSI-only.

## Manifest

There is one shared Flatpak manifest:

- `flathub/io.github.voltkraft.immich-folder-watch.yml` — the packaging source
  of truth. It remains tag + commit pinned for a future Flathub submission.
  During a GitHub release, `tools/prepare-flatpak-release-manifest.py` copies it
  to an ignored build directory, removes the not-yet-created tag, and pins the
  Git source to the exact commit used by the Windows MSI.

The release workflow builds `immich-folder-watch-<version>.flatpak` and the MSI
in parallel, then publishes neither unless both builds succeed. The separate
Flathub submission is currently postponed; see
[`flathub/README.md`](flathub/README.md) for the retained plan.

## Install a published bundle

Download the `.flatpak` file from GitHub Releases, then install it for the
current user:

```bash
flatpak install --user ./immich-folder-watch-<version>.flatpak
flatpak run io.github.voltkraft.immich-folder-watch
```

The bundle resolves its Freedesktop runtime from Flathub but does not configure
application updates. Download each new version manually and install it with
`flatpak install --user --or-update ./immich-folder-watch-<version>.flatpak`.

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
# 1) Pre-generate the offline NuGet feed. The Flatpak build sandbox has
#    no network access, so flatpak-builder hands dotnet a frozen package
#    list instead of running `dotnet restore`. Re-run this whenever the
#    NuGet dependency graph changes — most often an Avalonia or .NET
#    package version bump in src/ImmichFolderWatch.App.Linux/*.csproj.
#    A stale feed silently re-installs the OLD packages; when in doubt,
#    regenerate. The script reads the csproj graph from your working
#    tree, so make sure it matches the tag the manifest is pinned to.
./tools/generate-nuget-sources.sh
#    -> writes packaging/flatpak/flathub/nuget-sources.json

# 2) Create a manifest pinned to the current commit. The commit must
#    already be available from the upstream Git repository.
mkdir -p artifacts/flatpak-local
python3 tools/prepare-flatpak-release-manifest.py \
    --source packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml \
    --output artifacts/flatpak-local/io.github.voltkraft.immich-folder-watch.yml \
    --commit "$(git rev-parse HEAD)"
cp packaging/flatpak/flathub/nuget-sources.json \
    artifacts/flatpak-local/nuget-sources.json

# 3) Build + install into the user Flatpak repo.
flatpak-builder --user --install --force-clean \
    artifacts/flatpak-local/build-dir \
    artifacts/flatpak-local/io.github.voltkraft.immich-folder-watch.yml

# 4) Run it (from a terminal so log output is visible).
flatpak run io.github.voltkraft.immich-folder-watch
```

The generated manifest builds **exactly the selected commit**, matching the
GitHub release job without requiring the release tag to exist first.

### Iterating on local (un-pushed) changes

To build uncommitted or unpushed changes, change the Git source block only in
the generated manifest under `artifacts/flatpak-local/` to a local-dir source:

```yaml
    sources:
      - type: dir
        path: ../..
      - nuget-sources.json
```

The committed source manifest must remain `type: git`.

`artifacts/flatpak-local/`, `.flatpak-builder/`, and
`packaging/flatpak/flathub/nuget-sources.json` are gitignored and regenerated.

> **If a previous build is misbehaving in unexpected ways**, nuke the
> caches and start fresh — flatpak-builder happily reuses partial state,
> so a stale offline feed or an incremental cache hit can hide a real
> change:
>
> ```bash
> rm -rf .flatpak-builder artifacts/flatpak-local
> rm -f packaging/flatpak/flathub/nuget-sources.json
> ./tools/generate-nuget-sources.sh
> # Repeat steps 2-4 above.
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
Folder access is intentionally portal-based in the Flatpak package. The
current Avalonia tray backend needs a broad KDE D-Bus own-name grant that
Flathub no longer accepts for new apps, so the Flatpak package starts in
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
users will see on GitHub Releases and, in the future, Flathub. Run it before
tagging a release:

```bash
python3 tools/update-appstream.py 2.7.0 \
    --metainfo packaging/flatpak/io.github.voltkraft.immich-folder-watch.metainfo.xml
```

## Deferred Flathub submission

The Flathub manifest under `flathub/` already uses `type: git` with a
pinned tag/commit and a sibling `nuget-sources.json`.
[`flathub/README.md`](flathub/README.md) covers the pre-submission
checklist and future continuous-publishing flow. The submission is currently
postponed; GitHub Releases is the active Linux distribution channel.
