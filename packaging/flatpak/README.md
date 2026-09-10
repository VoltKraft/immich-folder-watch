# Flatpak Packaging

`immich-folder-watch` ships to Linux desktops as `x86_64` and `aarch64` Flatpak
bundles on **GitHub Releases**. The app builds against the freedesktop runtime
26.08 and uses a pinned Microsoft .NET 10 SDK only while building the Avalonia
head as a
self-contained `linux-x64` or `linux-arm64` publish.

App ID: `io.github.voltkraft.immich-folder-watch`

The current workflow adds the bundle to future releases. Existing releases
through `v2.7.0` remain MSI-only.

## Manifest

There is one shared Flatpak manifest:

- `flathub/io.github.voltkraft.immich-folder-watch.yml` — the packaging source
  of truth. Its example pin references a published release; preparation
  generates a matching tag + commit pin for each selected release.
  During a GitHub release, `tools/prepare-flatpak-release-manifest.py` copies it
  to an ignored build directory, removes the not-yet-created tag, and pins the
  Git source to the exact commit used by the Windows MSI.

The release workflow builds architecture-specific Windows and Linux packages in
parallel, then publishes none unless all four builds succeed. The Flatpak names
are `immich-folder-watch-<version>-linux-x64.flatpak` and
`immich-folder-watch-<version>-linux-arm64.flatpak`. Flathub preparation runs after
publication and generates a complete feed for both architectures. Initial
acceptance and update activation are still pending;
see [`flathub/README.md`](flathub/README.md) for requirements and setup.

## Install a published bundle

Download the bundle matching `flatpak --default-arch` from GitHub Releases:
use the `linux-x64` file for `x86_64` and the `linux-arm64` file for `aarch64`.
Then install it for the current user:

```bash
flatpak install --user ./immich-folder-watch-<version>-linux-<architecture>.flatpak
flatpak run io.github.voltkraft.immich-folder-watch
```

The bundle resolves its Freedesktop runtime from Flathub but does not configure
application updates. Download each new version manually and install it with
`flatpak install --user --or-update ./immich-folder-watch-<version>-linux-<architecture>.flatpak`.

## Local build

Prerequisites on the dev machine (Fedora shown; Debian/Ubuntu in parens):

```bash
sudo dnf install flatpak flatpak-builder    # apt install flatpak flatpak-builder
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub \
  org.freedesktop.Platform//26.08 \
  org.freedesktop.Sdk//26.08
```

Install the exact host .NET SDK reported by this command and put its `dotnet`
executable on `PATH` before generating the feed:

```bash
python3 tools/read-flatpak-sdk.py \
  --manifest packaging/flatpak/flathub/io.github.voltkraft.immich-folder-watch.yml \
  --format version
```

The generator selects that exact SDK with roll-forward disabled. It restores
against nuget.org in fresh temporary package/HTTP caches and verifies archive
bytes against NuGet's checksum records. It does not need a Flatpak SDK extension,
reuse the user's NuGet cache, or replace an existing feed when restore fails.

Then, from the repo root:

```bash
# 1) Pre-generate the offline NuGet feed. The Flatpak build sandbox has
#    no network access, so flatpak-builder hands dotnet a frozen package
#    list for its offline restore. Re-run this whenever the
#    NuGet dependency graph changes — most often an Avalonia or .NET
#    package version bump in src/ImmichFolderWatch.App.Linux/*.csproj.
#    Missing packages fail the offline restore; regenerate the complete feed.
#    The script reads the working tree, which must match the source commit.
./tools/generate-nuget-sources.sh --runtime linux-x64
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
For an ARM64 build, run the same steps on an `aarch64` host and pass
`--runtime linux-arm64` when generating the NuGet source list. The manifest
maps the Flatpak architecture to the corresponding .NET runtime automatically.

### Iterating on local (un-pushed) changes

To build uncommitted or unpushed changes, change the Git source block only in
the generated manifest under `artifacts/flatpak-local/` to a local-dir source,
keeping the SDK archive entries and NuGet source list intact:

```yaml
    sources:
      - type: dir
        path: ../..
      # Keep the existing architecture-specific SDK archive sources here.
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
> ./tools/generate-nuget-sources.sh --runtime linux-x64
> # Repeat steps 2-4 above.
> ```

## Sandbox permissions

The manifest grants the following static permissions:

| `finish-args` | What it enables |
|---|---|
| `--share=ipc` + `--socket=x11` | X11/XWayland display access. Avalonia's current Linux backend initializes X11. |
| `--share=network` | Talk to the Immich server (HTTP + Socket.IO) |
| `--device=dri` | GPU compositor for Avalonia |
| `--talk-name=org.kde.StatusNotifierWatcher` | Register the tray item with the desktop |

Notably **not** granted: `--filesystem=host`, `flatpak-spawn --host`,
`--filesystem=home`, `--filesystem=xdg-pictures`,
`--filesystem=xdg-videos`, `--talk-name=org.freedesktop.systemd1`, raw
`--socket=session-bus`, `--socket=wayland`, or broad KDE own-name permissions.
Folder access and notifications use portals. Notifications call
`org.freedesktop.portal.Notification.AddNotification` through Flatpak's implicit
portal access; no direct notification-daemon permission is granted. The tray exports StatusNotifierItem and
DBusMenu on `io.github.voltkraft.immich-folder-watch.Tray`, which Flatpak already
allows in the application's own namespace. KDE Plasma and GNOME with an
AppIndicator extension provide the watcher. Without one, the app displays a
notice and remains reachable through its window and launcher.

Verify at runtime with:

```bash
flatpak permissions io.github.voltkraft.immich-folder-watch
flatpak info -M io.github.voltkraft.immich-folder-watch
```

## Branding assets

The application build generates the launcher icon from `assets/branding/logo.svg`
through `tools/BrandAssetGen`. The manifest installs the current square 512×512
PNG from `artifacts/branding/flatpak/`; the legacy copies under
`packaging/flatpak/icons/` are not used by the build. The source logo may use a
tightly cropped, rectangular canvas, so its SVG is not exported as a Flatpak
launcher icon: Flatpak requires square icon dimensions.

## SDK maintenance

The two architecture-filtered SDK archive entries in the shared manifest are
the single source of truth for the version, official download URLs and SHA-512
pins. `tools/read-flatpak-sdk.py` validates those entries; feed generation and
Actions setup read the same version. The archives unpack under the module's
`dotnet-sdk` build directory and are not installed under `/app`.

For a .NET SDK/security update, obtain both Linux architecture archives and hashes
from [Microsoft's release metadata](https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json),
verify their bytes, update both manifest entries together, install that exact
host SDK, and regenerate both feeds. Run native CI for both architectures and
review any new package versions against the notice catalog below. Runtime upgrades
also require testing the exported packages. CI currently runs Builder in the
published `freedesktop-25.08` tooling image, because the `freedesktop-26.08` image
tag is not yet available. Builder's `--install-deps-from=flathub` installs the
manifest's actual 26.08 runtime and SDK; the outer container does not select the
application ABI. Switch the tooling image once its 26.08 tag is published. Do not
combine mismatched SDK-extension and runtime branches.

## License notices

Flatpak Builder copies the application license. The build also installs
`THIRD_PARTY_NOTICES.md` and runs `tools/install-flatpak-license-notices.py` to
collect package-supplied licenses and notices from the offline NuGet archives.
Versioned supplemental texts under `licenses/` cover packages that omit them.
Their source provenance is recorded beside the files. The installed inventory
describes the complete build feed, including build-only and other-platform
inputs; it is not a list of runtime-shipped assemblies. Unknown package versions
that require supplements must be reviewed before a dependency update can build.

## Release-time AppStream block

`tools/update-appstream.py <version>` reads the matching `## [<version>]`
section from `CHANGELOG.md` and prints an AppStream `<release>` block. Add `--metainfo` to write it into
`io.github.voltkraft.immich-folder-watch.metainfo.xml`, filtering out items
tagged `(Windows)` so the Linux-facing metadata only documents what Linux
users will see on GitHub Releases and, in the future, Flathub. Run it before
tagging a release:

```bash
python3 tools/update-appstream.py 2.8.0 \
    --metainfo packaging/flatpak/io.github.voltkraft.immich-folder-watch.metainfo.xml
```

## Flathub submission and updates

The Flathub manifest under `flathub/` already uses `type: git` with a
pinned tag/commit and a sibling `nuget-sources.json`.
[`flathub/README.md`](flathub/README.md) covers the pre-submission
requirements, current blockers and activation of release-triggered updates.
GitHub Releases remains available while initial Flathub acceptance is pending.
