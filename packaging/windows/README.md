# Windows Packaging

This directory contains the first automation-friendly Windows packaging flow.

## Included

- `build-installer.ps1`: publishes the daemon and assembles a distributable bundle
- `build-msi.ps1`: publishes the daemon and builds an `.msi` installer with WiX
- `install-service.ps1`: installs or updates the service on a Windows host
- `uninstall-service.ps1`: removes the service and installed binaries
- `service-management.ps1`: shared helpers for robust stop/delete/wait service operations
- `ImmichFolderWatch.Setup.wixproj` / `Installer.wxs`: WiX authoring for the MSI package
- `installer.stub.md`: notes on future bootstrapper `.exe` scope

## Current Status

- Script-based Windows installation is implemented.
- MSI packaging is implemented.
- A bootstrapper `.exe` is still planned.
