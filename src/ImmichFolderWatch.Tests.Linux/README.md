# Linux GUI regression tests

Run the real Avalonia views with an isolated headless application:

```bash
dotnet test src/ImmichFolderWatch.Tests.Linux/ImmichFolderWatch.Tests.Linux.csproj -c Debug
```

The fixture supplies synthetic configuration and never starts the production
application, Immich connections, folder workers, portals, or autostart services.
Tests exercise actual controls and bindings, source draft retention, sync-mode
tab visibility, API-key masking, status colors, close/reopen behavior, session
logging, and layout at the supported minimum window size. These checks do not
replace desktop acceptance tests for Flatpak portals, tray integration, or logout.

Additional tests cover stale access-check cancellation and host start/restart
cleanup. Lifecycle tests use fake hosts and an unpumped UI synchronization context
to detect shutdown deadlocks without launching workers or contacting Immich.

To export all eight main pages in both themes for visual review:

```bash
IFW_UI_PREVIEW_DIRECTORY="$PWD/artifacts/ui-preview/linux" \
  dotnet test src/ImmichFolderWatch.Tests.Linux/ImmichFolderWatch.Tests.Linux.csproj \
  -c Debug --filter FullyQualifiedName~MainPages_RenderAtMinimumSize
```

The 16 PNG files contain synthetic data. They are generated artifacts and must
not be committed. They support visual review; tests do not compare pixels against
platform-dependent golden images.

The test setup follows the [official Avalonia headless xUnit documentation](https://docs.avaloniaui.net/docs/testing/headless-xunit).
`Avalonia.Headless.XUnit` is pinned to the application's Avalonia version. Version
12.0.3 requires xUnit v3, so this test project uses xUnit 3.2.2 while the existing
test projects retain their current versions. The Visual Studio runner preserves
the repository's `dotnet test`/VSTest workflow.

Dependency license review: Avalonia Headless is
[MIT](https://github.com/AvaloniaUI/Avalonia/blob/12.0.3/licence.md);
xUnit v3 is [Apache-2.0](https://github.com/xunit/xunit/blob/v3-3.2.2/LICENSE),
and the xUnit Visual Studio runner 3.1.5 declares Apache-2.0 in its published
NuGet metadata. Both licenses are compatible with this repository's AGPL-3.0-only
license. These dependencies are used only by the test project.

Linux protocol tests require `dbus-daemon` and `xdg-dbus-proxy`. They run on
isolated buses and include the same app-ID namespace ownership and watcher
talk rule used by Flatpak. Document-path tests cover opaque IDs, nested paths,
xattr lookup, denied/older portals, timeout and cancellation.

When running the full solution on Windows, the six native tray protocol tests
and three document-portal protocol tests are reported as skipped by `LinuxFact`.
Platform-neutral document-path, lifecycle, session, access-check and headless GUI
checks remain enabled. On Linux, missing protocol tools fail the corresponding
tests rather than silently reducing coverage; the Linux CI job installs them.
