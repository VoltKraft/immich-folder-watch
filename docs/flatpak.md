# Flatpak Notes

`immich-folder-watch` is packaged as an `x86_64` Flatpak and distributed as a
single-file bundle through future **GitHub Releases** created by the current
workflow (app ID `io.github.voltkraft.immich-folder-watch`). Releases through
`v2.7.0` are not backfilled.

All Flatpak packaging lives under `packaging/flatpak/`:

- [`packaging/flatpak/README.md`](../packaging/flatpak/README.md) —
  building the Flatpak locally, the sandbox permission set, and branding
  assets.
- [`packaging/flatpak/flathub/README.md`](../packaging/flatpak/flathub/README.md)
  — the postponed Flathub submission and continuous-publishing plan.

The app builds against the freedesktop runtime 25.08 + the .NET 10 SDK
extension, runs entirely per-user (no daemon, no root), and accesses
watch folders through the FileChooser / Documents portals. The release
workflow builds the bundle from the manifest under
`packaging/flatpak/flathub/`, temporarily pinning its Git source to the same
commit used for the Windows MSI. The GitHub bundle must be reinstalled manually
for each application update. Publication through Flathub is currently
postponed.
