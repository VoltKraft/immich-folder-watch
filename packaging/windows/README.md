# Windows Packaging

This directory contains the automation-friendly Windows packaging flow.

## Included

- `build-msi.ps1`: publishes `ImmichFolderWatch.App` and builds an `.msi` installer with WiX
- `config.windows.example.yaml`: per-user config template (for reference only, no longer embedded in the MSI)
- `ImmichFolderWatch.Setup.wixproj` / `Installer.wxs`: WiX authoring for the MSI package
- `installer.stub.md`: notes on future bootstrapper `.exe` scope

## Current Status

- Native x64 and ARM64 MSI packages are the supported end-user installation
  paths. GitHub Releases publishes both, and the shared WinGet package selects
  the matching architecture.
- A bootstrapper `.exe` is still planned.

Build either package from Windows with:

```powershell
.\packaging\windows\build-msi.ps1 -Runtime win-x64
.\packaging\windows\build-msi.ps1 -Runtime win-arm64
```

The resulting names are `immich-folder-watch-<version>-win-x64.msi` and
`immich-folder-watch-<version>-win-arm64.msi`.

The WiX project disables hard links when copying build outputs, including
`.wixpdb` files, from `obj` to the package output directory. This keeps the
outputs compatible with cloud sync providers such as Nextcloud on Windows.
The setting applies both to `build-msi.ps1` and direct builds of the WiX project.
Existing hard-linked outputs must be replaced with independent copies once;
an incremental build may otherwise keep them because their contents are unchanged.

## Default Layout

- `%ProgramFiles%\Immich Folder Watch\bin\`: app binaries and runtime files
- `%LOCALAPPDATA%\Immich Folder Watch\config.yaml`: per-user active config
- `%LOCALAPPDATA%\Immich Folder Watch\logs\`: per-user app logs
- `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Immich Folder Watch.lnk`: autostart shortcut (default on)

Each Windows user has an independent config and log directory. The app runs as a user-context process (tray icon + optional main window). No Windows service is installed.

## Upgrade From Legacy Service Installs

When upgrading from a version that installed the `ImmichFolderWatch` Windows service:

- The legacy service is stopped and deleted.
- The existing `C:\ProgramData\Immich Folder Watch\config.yaml` is copied to the installing user's `%LOCALAPPDATA%\Immich Folder Watch\config.yaml` (only for the account running the MSI).
- The `C:\ProgramData\Immich Folder Watch\` folder is removed.
- Autostart is enabled by default.

Other Windows users on the same machine keep using the app after their first launch, which seeds a fresh per-user config.

## Upgrade process safety

The MSI requests application shutdown before `InstallValidate`, then aborts with
an explanatory error if any `ImmichFolderWatch.exe` process remains. It does not
force-terminate a worker before synchronization can finish. Close the application
for all signed-in users before retrying an aborted update. Old-product removal
runs immediately after `InstallInitialize`, inside the rollback transaction.
This avoids deliberately uninstalling the old payload before asking its process
to exit; file-in-use/reboot behavior still requires Windows upgrade testing.

`Test-InstallerUpgradeContract.ps1` reads the compiled MSI with Windows Installer's
read-only COM API. Packaging fails if shutdown/abort/removal ordering or the
synchronous close flags are wrong. Keep these actions in the linked `Package`:
unreferenced WiX fragments can be omitted from the output. Windows CI runs the
checker regression tests and builds both architecture candidates with this gate.
The x64 candidate is installed on a fresh GitHub-hosted Windows runner by
`Test-InstalledUpgrade.ps1`: verified public 3.0.3 is launched, then upgraded
while its WPF process has the app-local runtime loaded. The harness verifies
all published payload hashes, replacement product registration, preserved
synthetic configuration and successful candidate startup. No Immich connection
or personal media is configured. It uninstalls the disposable product afterward.
MSI logs, file hashes and `upgrade-result.json` are uploaded as
`windows-upgrade-evidence`, including on failure. MSI exit 3010 or deferred
application file operations fail acceptance instead of claiming a reboot test.

CI uses MSI version 3.0.4 solely to exercise the major-upgrade path from 3.0.3;
it does not modify the product version or publish a release. The old and new
runtime may have the same version, intentionally exercising runtime retention.
ARM64 packages are compiled/validated but not executed on the x64 runner.

The 2026-11-13 incident confirmed missing installed runtime files and recovery
through MSI repair. The released MSI contained those files, but its explicit
close action was sequenced after old-product removal. That ordering defect is
corrected; the user's exact deletion mechanism remains unproven without the
original update log. Acceptance still requires a Windows upgrade with the old
tray process running, comparing runtime files before/after and after any reboot,
verifying application startup and preserving per-user configuration.
