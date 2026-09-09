# Linux desktop feature parity

The Linux host implements the Windows desktop capabilities through the same
Core, Immich integration, and shared view model. Desktop permission and packaging
differences remain intentional. This matrix records the implementation and its
automated verification; it does not substitute headless tests for native desktop
acceptance.

| Capability | Implementation and verification |
| --- | --- |
| Upload new, upload all, bidirectional sync, albums, filters, deletion, transfer order, batching and retry | Both hosts register the same worker, API clients, queue and SQLite store. The portable configuration, worker persistence, API and status suites exercise these behaviors. Linux control tests cover mode changes and retained source drafts. |
| Validate, save and apply | Both windows use `ConfigApplyService` and `AppConfigWriter`. Tests verify invalid local settings and denied permissions never write/restart, successful apply awaits the normalized restart, and write/restart failures are surfaced. |
| Initial and manual connection checks | Linux starts an access check during bootstrap. `ImmichAccessCheckSession` makes the newest request authoritative; saving cancels the previous check. Tests exercise a slow checker, ignored cancellation, replacement, failure and shutdown. Results from obsolete credentials or permission requirements are discarded. |
| Language | Both hosts apply startup language and persist it through the shared view model. Tests cover configured `auto`, `en`, `de`, changing the selection, and save/reload. |
| Autostart | Linux requests approval once on fresh setup. The shared view model stays responsive and serializes changes. Tests cover approval, denial, timeout, cancellation, existing installations, and initialization/toggle races. |
| Background operation and shutdown | Closing hides the window; explicit Quit closes it after stopping synchronization. Headless tests exercise hide/reopen and explicit close. Portal tests verify hiding preserves confirmed autostart. Host lifecycle tests verify pending start/restart, cancellation and disposal without UI dispatch, including partial-start cleanup and retry. Connection disposal cancels pending and queued bus connections. |
| Tray where supported | Linux provides localized Open, Restart and Quit. The tooltip tracks connectivity, last sync and queue size. Portable tests verify text updates and language changes; native tray rendering is a desktop smoke check. |
| Folder editing | Linux uses Choose Folder to replace/renew a portal grant while keeping source settings. Headless tests verify the displayed host path remains read-only and separate from the saved access path, including selection after removal/re-add. |
| Status, API key and navigation | Real Avalonia controls are tested for masking/reveal, semantic status tones, live theme changes, draft retention, source modes and tab visibility. |
| Logs | File logging opens its directory. Journald opens a Flatpak-safe viewer of the latest 500 session entries; persistent history remains in the journal. Tests verify bounded retention, long-entry truncation, worker-provider replacement and the read-only window. XDG defaults are covered by view-model tests; legacy relative log directories are resolved against the configuration directory. |
| Version and update hints | Both hosts use the existing shared GitHub checker, version provider and update view-model state. Existing update tests remain part of the portable suite. |

## Intentional platform differences

- Flatpak retains its restricted permissions, portal folder access, X11/XWayland
  runtime and disabled tray. Autostart opens its window; the launcher reopens a
  hidden window. No broad filesystem or D-Bus permission was added.
- Autostart requires portal approval. The local flag records the last confirmed
  response; the portal offers no query for changes made outside the application.
  `autostart-initialized` records that first-run setup was offered, while the
  existing `autostart-requested` file records confirmed enablement. Existing
  configurations are not automatically opted in. No YAML migration is needed.
- Windows uses Event Viewer and Startup-folder shortcuts. Linux uses Journald,
  the session viewer, and the Background portal. System journal history is viewed
  through host tools rather than granting the sandbox access to host logs.
- Windows legacy installer migration and MSI/WinGet packaging remain specific to
  Windows. Flatpak bundles retain their existing installation/update workflow.

## Automated checks

```bash
dotnet build src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj -c Debug
dotnet test src/ImmichFolderWatch.Tests.Core/ImmichFolderWatch.Tests.Core.csproj -c Debug
dotnet test src/ImmichFolderWatch.Tests.Linux/ImmichFolderWatch.Tests.Linux.csproj -c Debug
```

The portal protocol tests start an isolated `dbus-daemon` and a fake portal on
Linux. They verify signal subscription, early/legacy handles, unrelated signals,
method errors, request cancellation/timeout and `Request.Close` using actual
D-Bus messages. They do not contact the user's desktop bus.

The [Linux GUI fixture](../../src/ImmichFolderWatch.Tests.Linux/README.md) renders
all eight pages in light and dark themes with synthetic data and checks the
minimum window size. Generated images stay under `artifacts/ui-preview/`.

Native portal dialogs, real tray hosts, login/logout, live Immich and release
packages require the corresponding [desktop smoke tests](linux-smoke.md).

## Validation on 2026-09-09

- Linux Debug host built successfully.
- The complete portable suite passed 332/332 tests, including 19 Linux platform
  cases and eight isolated D-Bus/socket protocol cases.
- The Linux GUI/session/lifecycle suite passed 18/18 tests. Sixteen synthetic page renders
  were inspected in light and dark themes; footer layout also passed at 960×680.
- The Windows WPF Debug host cross-compiled successfully on Linux. Restore could
  not retrieve NuGet vulnerability data (`NU1900`); there were no compile errors.
  Windows test execution and MSI creation were not performed on this Linux host.
- Native desktop consent, tray rendering, login/logout, Flatpak package building
  and live Immich were not exercised in this validation run.
