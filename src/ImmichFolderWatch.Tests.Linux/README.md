# Linux GUI regression tests

Run the real Avalonia views with an isolated headless application:

```bash
dotnet test src/ImmichFolderWatch.Tests.Linux/ImmichFolderWatch.Tests.Linux.csproj -c Debug
```

The fixture supplies synthetic configuration and never starts the production
application, Immich connections, folder workers, portals, or autostart services.
Tests exercise actual controls and bindings, source draft retention, sync-mode
tab visibility, API-key masking, status colors, close/reopen behavior, startup-only
tray fallback and hidden-window preservation across tray outages/recovery, session
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
12.0.3 requires the xUnit v3 framework's 3.x extension API, so this test project
retains xUnit 3.2.2 while the portable and Windows projects use xUnit 2.9.3.
All three projects use Visual Studio runner 4.0.1, preserving the repository's
`dotnet test`/VSTest workflow.

Dependabot ignores `xunit.v3` versions 4.0.0 and newer until a compatible Avalonia
headless bridge is selected and validated. With the current bridge, 4.0.3 fails
GUI test discovery because `TestIntrospectionHelper.GetTestCaseDetails` changed
its binary interface. Its default MTP v2 integration also rejects the existing
VSTest mode on .NET 10. Merely replacing the obsolete parallelism attribute or
using `xunit.v3.mtp-off` does not fix the bridge incompatibility. Keep assembly-wide
test serialization for the shared Avalonia application/localization state.

Dependency license review: Avalonia Headless is
[MIT](https://github.com/AvaloniaUI/Avalonia/blob/12.0.3/licence.md);
xUnit v3 is [Apache-2.0](https://github.com/xunit/xunit/blob/v3-3.2.2/LICENSE),
and the [xUnit Visual Studio runner 4.0.1](https://www.nuget.org/packages/xunit.runner.visualstudio/4.0.1)
and [xUnit 2.9.3](https://www.nuget.org/packages/xunit/2.9.3) declare Apache-2.0 in
their official published NuGet metadata. Reviewed package provenance points to
runner commit `0f7d528729972578553fb146cbde5f95b316cdc4` and xUnit commit
`9712244020d385955d33136b3fe3e87de43539cd`. Both licenses are compatible with this
repository's AGPL-3.0-only license. These dependencies are test-only and are not
included in the application packages.

Linux protocol tests require `dbus-daemon` and `xdg-dbus-proxy`. They run on
isolated buses and include the same app-ID namespace ownership and watcher
talk rule used by Flatpak. Document-path tests cover opaque IDs, nested paths,
xattr lookup, denied/older portals, timeout and cancellation.
Notification tests use a synthetic portal on a bus without service activation,
verifying version-1 payloads, independent IDs, priorities, failures, timeout and
cancellation. A filtered proxy proves delivery needs portal access only, without
permission to call the notification daemon directly.

When running the full solution on Windows, native tray, document and notification
protocol tests are reported as skipped by `LinuxFact`.
Platform-neutral document-path, lifecycle, session, access-check and headless GUI
checks remain enabled. On Linux, missing protocol tools fail the corresponding
tests rather than silently reducing coverage; the Linux CI job installs them.
