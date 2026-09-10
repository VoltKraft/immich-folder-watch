# AppStream screenshots

The Flatpak AppStream metadata supplies screenshots to GNOME Software and,
when published there, Flathub. GitHub Releases remains the active Linux
distribution channel.

## Current selection

The metadata reuses the existing Linux images in `docs/qa/images/` without
copying them into this directory:

| File | Caption | Type |
|------|---------|------|
| `linux-folders-2.11.0.png` | Watch folders, album placement, and synchronization mode | default |
| `linux-logging-2.11.0.png` | Logging settings in the dark theme | additional |

These are renders of actual Avalonia controls with synthetic sample data.
See [Linux GUI validation](../../../docs/qa/linux-parity.md) for their context
and [the test instructions](../../../src/ImmichFolderWatch.Tests.Linux/README.md)
for reproducing the previews. The Windows images in `docs/images/` are not
used for the Linux listing. `GUI.png` is a historical image and is no longer
referenced by the metadata.

## Updating the selection

1. Capture or render the current Linux interface with useful sample content.
   Use English text and synthetic paths, URLs, and credentials only.
2. Inspect the PNGs for readability and layout before committing them.
3. Update the `<screenshots>` section in
   `../io.github.voltkraft.immich-folder-watch.metainfo.xml`. Keep exactly one
   `type="default"` entry and give each image a descriptive caption.
4. Pin raw GitHub image URLs to an existing published commit containing the
   inspected images. Do not move or recreate release tags to update screenshots.
5. Validate the metadata and check that each remote image matches its local file:

   ```bash
   appstreamcli validate --no-net packaging/flatpak/io.github.voltkraft.immich-folder-watch.metainfo.xml
   appstreamcli validate packaging/flatpak/io.github.voltkraft.immich-folder-watch.metainfo.xml
   ```

Run these commands from the repository root. Updated metadata ships with the
next Flatpak build; an already installed bundle and GNOME Software's cached
metadata do not change just because this repository file changes.
