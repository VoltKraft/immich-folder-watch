# Windows Packaging

This directory contains the first automation-friendly Windows packaging flow.

## Included

- `build-installer.ps1`: publishes the daemon and assembles a distributable bundle
- `install-service.ps1`: installs or updates the service on a Windows host
- `uninstall-service.ps1`: removes the service and installed binaries
- `installer.stub.md`: notes on future MSI/WiX scope

## Current Status

- Script-based Windows installation is implemented.
- MSI/WiX packaging is still planned.
