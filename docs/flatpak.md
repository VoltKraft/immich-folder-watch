# Flatpak Notes

Flatpak support is planned for a future milestone.

Current repository state:

- Placeholder manifest at `packaging/flatpak/io.github.immich_folder_watch.yaml`
- No active Flatpak workflow is currently wired into GitHub Actions
- App-ID-aligned icon assets are generated into `artifacts/branding/flatpak/`
  from the central `assets/branding/logo.svg`

## Goals

- Nextcloud-client style desktop integration
- Sandboxed packaging and distribution via Flathub
- Managed permissions for local folder access

## Current Limitation

The manifest is intentionally incomplete and marked as placeholder until runtime
dependencies and packaging strategy are finalized.
