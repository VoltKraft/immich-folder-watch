# Windows Packaging

This directory contains the first automation-friendly Windows packaging flow.

## Included

- `build-installer.ps1`: publishes the daemon, GUI, and admin helper and assembles a distributable bundle
- `build-msi.ps1`: publishes the daemon, GUI, and admin helper and builds an `.msi` installer with WiX
- `config.windows.example.yaml`: Windows-specific install template that targets the absolute install log path
- `install-service.ps1`: installs or updates the service on a Windows host
- `uninstall-service.ps1`: removes the service and installed binaries
- `service-management.ps1`: shared helpers for robust stop/delete/wait service operations
- `ImmichFolderWatch.Setup.wixproj` / `Installer.wxs`: WiX authoring for the MSI package
- `installer.stub.md`: notes on future bootstrapper `.exe` scope

## Current Status

- Script-based Windows installation is available for development and recovery scenarios.
- MSI packaging is the supported end-user installation path.
- A bootstrapper `.exe` is still planned.

## Default Layout

- `bin\`: daemon, GUI, admin helper, and runtime files
- `config\config.yaml`: active Windows config
- `config\activation-state.json`: first-verification state used by the GUI
- `logs\`: daemon logs

The GUI keeps the service status refreshed automatically and stores `logging.logDirectory` as an absolute path.

Legacy installs with `config.yaml` in the install root are migrated to `config\config.yaml` automatically if the structured config does not exist yet.
If both files exist, `config\config.yaml` stays active and the legacy file is left untouched.
