# Flatpak Notes

`immich-folder-watch` is packaged as a Flatpak and distributed via
**Flathub** (app ID `io.github.voltkraft.immich-folder-watch`).

All Flatpak packaging lives under `packaging/flatpak/`:

- [`packaging/flatpak/README.md`](../packaging/flatpak/README.md) —
  building the Flatpak locally, the sandbox permission set, and branding
  assets.
- [`packaging/flatpak/flathub/README.md`](../packaging/flatpak/flathub/README.md)
  — the Flathub submission and continuous-publishing flow.

The app builds against the freedesktop runtime 25.08 + the .NET 10 SDK
extension, runs entirely per-user (no daemon, no root), and accesses
watch folders through the FileChooser / Documents portals. Flathub builds
the app on its own infrastructure from the manifest under
`packaging/flatpak/flathub/`; the project does not build a `.flatpak`
bundle in CI.
