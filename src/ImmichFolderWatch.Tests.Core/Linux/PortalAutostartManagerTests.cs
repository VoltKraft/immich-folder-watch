using ImmichFolderWatch.App.Linux.Platform;
using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Linux;

public sealed class PortalAutostartManagerTests : IDisposable
{
    private readonly TestPaths _paths = new(Path.Combine(Path.GetTempPath(), "ifw-portal-" + Guid.NewGuid().ToString("N")));

    [Fact]
    public async Task EnableAsync_WaitsForConfirmedResponseBeforePersisting()
    {
        var completion = new TaskCompletionSource<BackgroundPortalResponse>(TaskCreationOptions.RunContinuationsAsynchronously);
        var portal = new FakePortal(_ => completion.Task);
        var manager = new PortalAutostartManager(portal, _paths);
        var enable = manager.EnableAsync();

        Assert.False(enable.IsCompleted);
        Assert.False(await manager.IsEnabledAsync());
        completion.SetResult(new(0, true, true));
        await enable;
        Assert.True(await new PortalAutostartManager(portal, _paths).IsEnabledAsync());
    }

    [Theory]
    [InlineData(0)]
    [InlineData(2)]
    public async Task EnableAsync_RejectsDeniedPermissionWithoutEnabling(uint code)
    {
        var manager = new PortalAutostartManager(new FakePortal(_ => Task.FromResult(new BackgroundPortalResponse(code, false, false))), _paths);
        await Assert.ThrowsAsync<InvalidOperationException>(() => manager.EnableAsync());
        Assert.False(await manager.IsEnabledAsync());
    }

    [Fact]
    public async Task DisableAsync_CancelledDialogPreservesConfirmedAutostart()
    {
        var portal = new FakePortal(_ => Task.FromResult(new BackgroundPortalResponse(0, true, true)));
        var manager = new PortalAutostartManager(portal, _paths);
        await manager.EnableAsync();
        portal.Response = _ => Task.FromResult(new BackgroundPortalResponse(1, false, false));

        await Assert.ThrowsAsync<OperationCanceledException>(() => manager.DisableAsync());
        Assert.True(await manager.IsEnabledAsync());
    }

    [Fact]
    public async Task EnableAsync_TimeoutPreservesStateAndReleasesGateForRetry()
    {
        var portal = new FakePortal(_ => Task.FromException<BackgroundPortalResponse>(new TimeoutException()));
        var manager = new PortalAutostartManager(portal, _paths);
        await Assert.ThrowsAsync<TimeoutException>(() => manager.EnableAsync());
        Assert.False(await manager.IsEnabledAsync());
        portal.Response = _ => Task.FromResult(new BackgroundPortalResponse(0, true, true));
        await manager.EnableAsync().WaitAsync(TimeSpan.FromSeconds(2));
        Assert.True(await manager.IsEnabledAsync());
    }

    [Fact]
    public async Task BackgroundRequest_WaitsForPendingEnableAndPreservesAutostart()
    {
        var completion = new TaskCompletionSource<BackgroundPortalResponse>(TaskCreationOptions.RunContinuationsAsynchronously);
        var portal = new FakePortal(_ => completion.Task);
        var manager = new PortalAutostartManager(portal, _paths);
        var enable = manager.EnableAsync();
        var background = manager.RequestBackgroundPermissionAsync();
        Assert.Single(portal.Requests);
        completion.SetResult(new(0, true, true));
        await Task.WhenAll(enable, background).WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Equal(new[] { true, true }, portal.Requests);
        Assert.True(await manager.IsEnabledAsync());
    }

    [Fact]
    public async Task BackgroundClient_RequestsOnceAndRetainsEnabledAutostart()
    {
        var portal = new FakePortal(enabled => Task.FromResult(new BackgroundPortalResponse(0, true, enabled)));
        var manager = new PortalAutostartManager(portal, _paths);
        await manager.EnableAsync();
        var client = new BackgroundPortalClient(manager, NullLogger<BackgroundPortalClient>.Instance);
        await client.RequestBackgroundAsync();
        await client.RequestBackgroundAsync();
        Assert.Equal(new[] { true, true }, portal.Requests);
        Assert.True(await manager.IsEnabledAsync());
    }

    [Fact]
    public async Task InitializeAsync_DeniedFirstRunIsNotRepeatedAndSettingsCanRetry()
    {
        var portal = new FakePortal(_ => Task.FromResult(new BackgroundPortalResponse(2, false, false)));
        await new PortalAutostartManager(portal, _paths).InitializeAsync(false);
        var nextRun = new PortalAutostartManager(portal, _paths);
        await nextRun.InitializeAsync(false);
        Assert.Single(portal.Requests);
        Assert.False(await nextRun.IsEnabledAsync());
        portal.Response = _ => Task.FromResult(new BackgroundPortalResponse(0, true, true));
        await nextRun.EnableAsync();
        Assert.True(await nextRun.IsEnabledAsync());
    }

    [Fact]
    public async Task InitializeAsync_ExistingConfigurationDoesNotRequestAutostart()
    {
        var portal = new FakePortal(_ => throw new InvalidOperationException("No request expected"));
        await new PortalAutostartManager(portal, _paths).InitializeAsync(true);
        Assert.Empty(portal.Requests);
    }

    [Fact]
    public async Task BackgroundRequest_RecordsActualRevokedAutostart()
    {
        var portal = new FakePortal(_ => Task.FromResult(new BackgroundPortalResponse(0, true, true)));
        var manager = new PortalAutostartManager(portal, _paths);
        await manager.EnableAsync();
        portal.Response = _ => Task.FromResult(new BackgroundPortalResponse(0, false, false));
        Assert.False(await manager.RequestBackgroundPermissionAsync());
        Assert.False(await manager.IsEnabledAsync());
        await manager.RequestBackgroundPermissionAsync();
        Assert.Equal(new[] { true, true, false }, portal.Requests);
    }

    public void Dispose()
    {
        if (Directory.Exists(_paths.Root)) Directory.Delete(_paths.Root, true);
    }

    private sealed class FakePortal(Func<bool, Task<BackgroundPortalResponse>> response) : IBackgroundPortalRequest
    {
        public Func<bool, Task<BackgroundPortalResponse>> Response { get; set; } = response;
        public List<bool> Requests { get; } = [];
        public Task<BackgroundPortalResponse> RequestAsync(bool autostart, CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Requests.Add(autostart);
            return Response(autostart);
        }
    }

    private sealed record TestPaths(string Root) : IPlatformPaths
    {
        public string ProductFolderName => "test";
        public string GetUserDataRoot() => Root;
        public string GetConfigPath() => Path.Combine(Root, "config.json");
        public string GetSyncDatabasePath() => Path.Combine(Root, "sync-state.db");
        public string GetLogDirectory() => Path.Combine(Root, "logs");
    }
}
