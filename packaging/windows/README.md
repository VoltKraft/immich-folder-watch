# Windows Packaging

This directory contains the first automation-friendly Windows packaging flow.

## Included

- `build-installer.ps1`: publishes the daemon, GUI, and admin helper and assembles a distributable bundle
- `build-msi.ps1`: publishes the daemon, GUI, and admin helper and builds an `.msi` installer with WiX
- `config.windows.example.yaml`: Windows-specific install template that targets the ProgramData log path
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

- `%ProgramFiles%\Immich Folder Watch\bin\`: daemon, GUI, admin helper, and runtime files
- `C:\ProgramData\Immich Folder Watch\config.yaml`: active Windows config
- `C:\ProgramData\Immich Folder Watch\logs\`: daemon logs

The GUI keeps the service status refreshed automatically, verifies the config on every save, stores `logging.logDirectory` as an absolute path, and migrates existing logs when the configured log directory changes successfully through the GUI.

Legacy installs with `%ProgramFiles%\Immich Folder Watch\config\config.yaml` or `%ProgramFiles%\Immich Folder Watch\config.yaml` are migrated to `C:\ProgramData\Immich Folder Watch\config.yaml` automatically.
If the old config still used `%ProgramFiles%\Immich Folder Watch\logs\`, those logs are moved to `C:\ProgramData\Immich Folder Watch\logs\` as well.
