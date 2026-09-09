using ImmichFolderWatch.App.Linux.Hosting;
using ImmichFolderWatch.App.Linux.Logging;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

public sealed class AppHostLifecycleTests
{
    [Fact]
    public async Task RestartAsync_CancelledDuringStop_AllowsBackgroundDisposalWithoutPumpingUiContext()
    {
        var stopStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var stopCompletion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var first = new FakeHost
        {
            Stop = token =>
            {
                stopStarted.SetResult();
                return stopCompletion.Task.WaitAsync(token);
            },
        };
        var replacement = new FakeHost();
        var hosts = new Queue<IHost>([first, replacement]);
        var host = CreateHost(_ => hosts.Dequeue());
        await host.StartAsync(CreateConfig(), TestContext.Current.CancellationToken);
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        var uiContext = new UnpumpedSynchronizationContext();

        var restart = StartWithContext(uiContext, () => host.RestartAsync(CreateConfig(), cancellation.Token));
        await stopStarted.Task.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        Assert.False(restart.IsCompleted);
        cancellation.Cancel();
        var disposal = Task.Run(async () => await host.DisposeAsync(), TestContext.Current.CancellationToken);

        await disposal.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => restart);
        Assert.Equal(0, uiContext.PostCount);
        Assert.Equal(1, first.DisposeCount);
        Assert.Equal(1, replacement.DisposeCount);
        Assert.False(host.IsRunning);
    }

    [Fact]
    public async Task StartAsync_PendingStart_AllowsBackgroundDisposalWithoutPumpingUiContext()
    {
        var startCompletion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var partialHost = new FakeHost { Start = token => startCompletion.Task.WaitAsync(token) };
        var host = CreateHost(_ => partialHost);
        var uiContext = new UnpumpedSynchronizationContext();
        var start = StartWithContext(uiContext, () => host.StartAsync(CreateConfig(), TestContext.Current.CancellationToken));
        Assert.False(start.IsCompleted);
        Assert.False(host.IsRunning);
        var disposal = Task.Run(async () => await host.DisposeAsync(), TestContext.Current.CancellationToken);

        startCompletion.SetResult();

        await disposal.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        await start.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        Assert.Equal(0, uiContext.PostCount);
        Assert.Equal(1, partialHost.DisposeCount);
        Assert.False(host.IsRunning);
    }

    [Fact]
    public async Task StartAsync_FailedStart_DisposesPartialHostAndAllowsRetry()
    {
        var startCompletion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var failed = new FakeHost { Start = token => startCompletion.Task.WaitAsync(token) };
        var working = new FakeHost();
        var hosts = new Queue<IHost>([failed, working]);
        await using var host = CreateHost(_ => hosts.Dequeue());
        var failure = new InvalidOperationException("Synthetic start failure");
        var start = host.StartAsync(CreateConfig(), TestContext.Current.CancellationToken);
        Assert.False(host.IsRunning);

        startCompletion.SetException(failure);

        Assert.Same(failure, await Assert.ThrowsAsync<InvalidOperationException>(() => start));
        Assert.Equal(1, failed.DisposeCount);
        Assert.False(host.IsRunning);
        Assert.Null(host.CurrentConfig);
        var retryConfig = CreateConfig();
        await host.StartAsync(retryConfig, TestContext.Current.CancellationToken);
        Assert.True(host.IsRunning);
        Assert.Same(retryConfig, host.CurrentConfig);
        Assert.Equal(0, working.DisposeCount);
    }

    private static Task StartWithContext(SynchronizationContext context, Func<Task> operation)
    {
        var previous = SynchronizationContext.Current;
        SynchronizationContext.SetSynchronizationContext(context);
        try
        {
            return operation();
        }
        finally
        {
            SynchronizationContext.SetSynchronizationContext(previous);
        }
    }

    private static AppHost CreateHost(Func<AppConfig, IHost> factory) => new(
        new SyncStatusProvider(), new TestPlatformPaths(), new LinuxLoggingCapabilities(),
        new SessionLogBuffer(), factory);

    private static AppConfig CreateConfig() => new()
    {
        Immich = new ImmichSettings { ServerApiUrl = "https://immich.example/api", ApiKey = "test-key" },
        Watch = new WatchSettings { Sources = [new() { Path = Path.GetTempPath(), Extensions = [".jpg"] }] },
        Logging = new LoggingSettings { Target = LogTargets.Journald },
    };

    private sealed class UnpumpedSynchronizationContext : SynchronizationContext
    {
        private int _postCount;
        public int PostCount => Volatile.Read(ref _postCount);

        // A synchronous desktop shutdown blocks UI dispatch. Keep continuations unexecuted
        // so any accidental context capture causes the lifecycle assertions to time out.
        public override void Post(SendOrPostCallback callback, object? state) => Interlocked.Increment(ref _postCount);
    }

    private sealed class FakeHost : IHost
    {
        private int _disposeCount;
        public Func<CancellationToken, Task> Start { get; init; } = _ => Task.CompletedTask;
        public Func<CancellationToken, Task> Stop { get; init; } = _ => Task.CompletedTask;
        public int DisposeCount => Volatile.Read(ref _disposeCount);
        public IServiceProvider Services { get; } = new EmptyServiceProvider();

        public Task StartAsync(CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Start(cancellationToken);
        }

        public Task StopAsync(CancellationToken cancellationToken = default) => Stop(cancellationToken);
        public void Dispose() => Interlocked.Increment(ref _disposeCount);
    }

    private sealed class EmptyServiceProvider : IServiceProvider
    {
        public object? GetService(Type serviceType) => null;
    }

    private sealed class TestPlatformPaths : IPlatformPaths
    {
        public string ProductFolderName => "immich-folder-watch-tests";
        public string GetUserDataRoot() => Path.Combine(Path.GetTempPath(), ProductFolderName);
        public string GetConfigPath() => Path.Combine(GetUserDataRoot(), "config.yaml");
        public string GetSyncDatabasePath() => Path.Combine(GetUserDataRoot(), "sync-state.db");
        public string GetLogDirectory() => Path.Combine(GetUserDataRoot(), "logs");
    }
}
