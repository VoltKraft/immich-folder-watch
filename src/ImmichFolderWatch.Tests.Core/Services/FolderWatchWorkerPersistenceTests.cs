using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class FolderWatchWorkerPersistenceTests
{
    [Theory]
    [InlineData(WatchSourceSyncModes.UploadNew)]
    [InlineData(WatchSourceSyncModes.UploadAll)]
    public async Task DeleteAfterUpload_RemovesFileAfterVerifiedUpload(string syncMode)
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "photo.jpg");
        if (syncMode == WatchSourceSyncModes.UploadAll)
        {
            await File.WriteAllTextAsync(filePath, "photo");
        }

        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient();
        var config = CreateConfig(watchDirectory, syncMode, deleteAfterUpload: true);
        var initialReconciliationLogger = syncMode == WatchSourceSyncModes.UploadNew
            ? new InitialReconciliationLogger()
            : null;
        using var worker = CreateWorker(
            config,
            databasePath,
            client,
            workerLogger: initialReconciliationLogger);
        await worker.StartAsync(CancellationToken.None);

        if (syncMode == WatchSourceSyncModes.UploadNew)
        {
            await initialReconciliationLogger!.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
            await File.WriteAllTextAsync(filePath, "photo");
        }

        await client.WaitForUploadCountAsync(1, TimeSpan.FromSeconds(8));
        await WaitUntilAsync(() => !File.Exists(filePath), TimeSpan.FromSeconds(3));

        Assert.Equal(1, client.UploadCount);
        Assert.False(File.Exists(filePath));
        Assert.Empty(await GetEntriesAsync(config, databasePath));
        await worker.StopAsync(CancellationToken.None);
    }

    [Theory]
    [InlineData(WatchSourceSyncModes.UploadAll, false)]
    [InlineData(WatchSourceSyncModes.Sync, true)]
    public async Task DeleteAfterUpload_DoesNotDeleteWhenDisabledOrInSyncMode(
        string syncMode,
        bool deleteAfterUpload)
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "photo.jpg");
        await File.WriteAllTextAsync(filePath, "photo");

        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient();
        var config = CreateConfig(watchDirectory, syncMode, deleteAfterUpload);
        using var worker = CreateWorker(config, databasePath, client);
        await worker.StartAsync(CancellationToken.None);
        await client.WaitForUploadCountAsync(1, TimeSpan.FromSeconds(8));
        await Task.Delay(250);

        Assert.True(File.Exists(filePath));
        Assert.Single(await GetEntriesAsync(config, databasePath));
        await worker.StopAsync(CancellationToken.None);
    }

    [Fact]
    public async Task DeleteAfterUpload_DoesNotDeleteExistingUnverifiedUploadNewFile()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "photo.jpg");
        await File.WriteAllTextAsync(filePath, "photo");

        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient();
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadNew, deleteAfterUpload: true);
        using var worker = CreateWorker(config, databasePath, client);
        await worker.StartAsync(CancellationToken.None);
        await Task.Delay(TimeSpan.FromMilliseconds(1500));

        Assert.Equal(0, client.UploadCount);
        Assert.True(File.Exists(filePath));
        Assert.Empty(await GetEntriesAsync(config, databasePath));
        await worker.StopAsync(CancellationToken.None);
    }

    [Fact]
    public async Task DeleteAfterUpload_DoesNotDeleteAfterFailedUpload()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "photo.jpg");
        await File.WriteAllTextAsync(filePath, "photo");

        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient { FailUploads = true };
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadAll, deleteAfterUpload: true);
        using var worker = CreateWorker(config, databasePath, client);
        await worker.StartAsync(CancellationToken.None);
        await client.WaitForUploadCountAsync(1, TimeSpan.FromSeconds(8));

        Assert.True(File.Exists(filePath));
        Assert.Empty(await GetEntriesAsync(config, databasePath));
        await worker.StopAsync(CancellationToken.None);
    }

    [Fact]
    public async Task DeleteAfterUpload_DoesNotDeleteFileChangedDuringUpload()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "photo.jpg");
        await File.WriteAllTextAsync(filePath, "first");

        var uploadStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseUpload = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var client = new RecordingAssetClient
        {
            UploadHandler = async (count, cancellationToken) =>
            {
                if (count == 1)
                {
                    uploadStarted.TrySetResult();
                    await releaseUpload.Task.WaitAsync(cancellationToken);
                    return UploadAssetResult.Success("asset-1");
                }

                return UploadAssetResult.Failure(null, "retry intentionally failed");
            },
        };
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadAll, deleteAfterUpload: true);
        using var worker = CreateWorker(config, databasePath, client);
        await worker.StartAsync(CancellationToken.None);
        await uploadStarted.Task.WaitAsync(TimeSpan.FromSeconds(8));

        await File.WriteAllTextAsync(filePath, "second version with different size");
        releaseUpload.TrySetResult();
        await Task.Delay(500);

        Assert.True(File.Exists(filePath));
        Assert.Empty(await GetEntriesAsync(config, databasePath));
        await worker.StopAsync(CancellationToken.None);
    }

    [Fact]
    public async Task DeleteAfterUpload_RemovesPreviouslyVerifiedUploadWithoutReuploading()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "photo.jpg");
        await File.WriteAllTextAsync(filePath, "photo");

        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient();
        var initialConfig = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadAll);
        await RunUntilUploadCountAsync(initialConfig, databasePath, client, expectedCount: 1);

        var cleanupConfig = CreateConfig(
            watchDirectory,
            WatchSourceSyncModes.UploadAll,
            deleteAfterUpload: true);
        using var worker = CreateWorker(cleanupConfig, databasePath, client);
        await worker.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => !File.Exists(filePath), TimeSpan.FromSeconds(3));

        Assert.Equal(1, client.UploadCount);
        Assert.Empty(await GetEntriesAsync(cleanupConfig, databasePath));
        await worker.StopAsync(CancellationToken.None);
    }

    [Fact]
    public async Task DeleteAfterUpload_RetriesFailedDeletionWithoutReuploading()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "photo.jpg");
        await File.WriteAllTextAsync(filePath, "photo");

        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient();
        var deletionService = new FailOnceDeletionService();
        var config = CreateConfig(
            watchDirectory,
            WatchSourceSyncModes.UploadAll,
            deleteAfterUpload: true);
        using var worker = CreateWorker(config, databasePath, client, deletionService);
        await worker.StartAsync(CancellationToken.None);
        await client.WaitForUploadCountAsync(1, TimeSpan.FromSeconds(8));
        await WaitUntilAsync(() => !File.Exists(filePath), TimeSpan.FromSeconds(8));

        Assert.Equal(1, client.UploadCount);
        Assert.True(deletionService.AttemptCount >= 2);
        Assert.Empty(await GetEntriesAsync(config, databasePath));
        await worker.StopAsync(CancellationToken.None);
    }

    [Fact]
    public async Task RestartSkipsUnchangedFile_ThenUploadsSingleModification()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "photo.jpg");
        await File.WriteAllTextAsync(filePath, "first version");

        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient();
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadAll);

        await RunUntilUploadCountAsync(config, databasePath, client, expectedCount: 1);

        var syncConfig = CreateConfig(watchDirectory, WatchSourceSyncModes.Sync);
        using var secondWorker = CreateWorker(syncConfig, databasePath, client);
        await secondWorker.StartAsync(CancellationToken.None);
        await Task.Delay(TimeSpan.FromMilliseconds(1500));
        Assert.Equal(1, client.UploadCount);
        await secondWorker.StopAsync(CancellationToken.None);

        await File.WriteAllTextAsync(filePath, "second version with a different size");
        using var thirdWorker = CreateWorker(syncConfig, databasePath, client);
        await thirdWorker.StartAsync(CancellationToken.None);
        await client.WaitForUploadCountAsync(2, TimeSpan.FromSeconds(8));
        Assert.Equal(2, client.UploadCount);
        await thirdWorker.StopAsync(CancellationToken.None);

        using var fourthWorker = CreateWorker(syncConfig, databasePath, client);
        await fourthWorker.StartAsync(CancellationToken.None);
        await Task.Delay(TimeSpan.FromMilliseconds(1500));
        Assert.Equal(2, client.UploadCount);
        await fourthWorker.StopAsync(CancellationToken.None);

        var store = new SqliteSyncStateStore(databasePath);
        var scope = SyncAccountScope.Create(syncConfig.Immich.ServerApiUrl, syncConfig.Immich.ApiKey);
        var entry = Assert.Single(await store.GetSourceEntriesAsync(scope, watchDirectory));
        Assert.Equal("asset-2", entry.AssetId);
    }

    private static async Task RunUntilUploadCountAsync(
        AppConfig config,
        string databasePath,
        RecordingAssetClient client,
        int expectedCount)
    {
        using var worker = CreateWorker(config, databasePath, client);
        await worker.StartAsync(CancellationToken.None);
        await client.WaitForUploadCountAsync(expectedCount, TimeSpan.FromSeconds(8));
        var store = new SqliteSyncStateStore(databasePath);
        var scope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        var sourcePath = config.Watch.Sources.Single().Path;
        var deadline = DateTimeOffset.UtcNow + TimeSpan.FromSeconds(3);
        while ((await store.GetSourceEntriesAsync(scope, sourcePath)).Count == 0
            && DateTimeOffset.UtcNow < deadline)
        {
            await Task.Delay(25);
        }

        Assert.NotEmpty(await store.GetSourceEntriesAsync(scope, sourcePath));
        await worker.StopAsync(CancellationToken.None);
    }

    private static FolderWatchWorker CreateWorker(
        AppConfig config,
        string databasePath,
        RecordingAssetClient client,
        ILocalFileDeletionService? localFileDeletionService = null,
        ILogger<FolderWatchWorker>? workerLogger = null) =>
        new(
            config,
            new AlwaysReadyChecker(),
            localFileDeletionService ?? new LocalFileDeletionService(),
            new UploadBatchQueue(),
            client,
            new SqliteSyncStateStore(databasePath),
            new SyncStatusProvider(),
            workerLogger ?? NullLogger<FolderWatchWorker>.Instance);

    private static AppConfig CreateConfig(
        string watchDirectory,
        string syncMode,
        bool deleteAfterUpload = false) =>
        new()
        {
            Immich = new ImmichSettings
            {
                ServerApiUrl = "https://immich.example/api",
                ApiKey = "test-key",
            },
            Watch = new WatchSettings
            {
                BatchIntervalSeconds = 1,
                MaxBatchSize = 1,
                FileReadyTimeoutSeconds = 1,
                Sources =
                [
                    new WatchSourceSettings
                    {
                        Path = watchDirectory,
                        AlbumName = "Camera",
                        Extensions = [".jpg"],
                        SyncMode = syncMode,
                        DeleteAfterUpload = deleteAfterUpload,
                    },
                ],
            },
        };

    private static async Task<IReadOnlyList<SyncStateEntry>> GetEntriesAsync(
        AppConfig config,
        string databasePath)
    {
        var store = new SqliteSyncStateStore(databasePath);
        var scope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        return await store.GetSourceEntriesAsync(scope, config.Watch.Sources.Single().Path);
    }

    private static async Task WaitUntilAsync(Func<bool> condition, TimeSpan timeout)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
        while (!condition() && DateTimeOffset.UtcNow < deadline)
        {
            await Task.Delay(25);
        }

        Assert.True(condition(), "The expected condition was not reached before the timeout.");
    }

    private sealed class InitialReconciliationLogger : ILogger<FolderWatchWorker>
    {
        private const string ReconciliationMessagePrefix = "Persistent reconciliation for uploadNew";

        private readonly TaskCompletionSource _ready = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _reconciliationCount;

        public Task WaitUntilReadyAsync(TimeSpan timeout) => _ready.Task.WaitAsync(timeout);

        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(
            LogLevel logLevel,
            EventId eventId,
            TState state,
            Exception? exception,
            Func<TState, Exception?, string> formatter)
        {
            if (logLevel != LogLevel.Information
                || !formatter(state, exception).StartsWith(ReconciliationMessagePrefix, StringComparison.Ordinal))
            {
                return;
            }

            if (Interlocked.Increment(ref _reconciliationCount) == 2)
            {
                _ready.TrySetResult();
            }
        }
    }

    private sealed class AlwaysReadyChecker : IFileReadinessChecker
    {
        public Task<bool> WaitUntilReadyAsync(
            string filePath,
            TimeSpan timeout,
            CancellationToken cancellationToken) => Task.FromResult(true);
    }

    private sealed class RecordingAssetClient : IImmichAssetClient
    {
        private int _uploadCount;

        public int UploadCount => Volatile.Read(ref _uploadCount);

        public bool FailUploads { get; init; }

        public Func<int, CancellationToken, Task<UploadAssetResult>>? UploadHandler { get; init; }

        public Task PingAsync(CancellationToken cancellationToken) => Task.CompletedTask;

        public async Task<UploadAssetResult> UploadAssetAsync(
            UploadAssetRequest request,
            CancellationToken cancellationToken)
        {
            var count = Interlocked.Increment(ref _uploadCount);
            if (UploadHandler is not null)
            {
                return await UploadHandler(count, cancellationToken);
            }

            return FailUploads
                ? UploadAssetResult.Failure(null, "upload intentionally failed")
                : UploadAssetResult.Success($"asset-{count}");
        }

        public async Task WaitForUploadCountAsync(int expectedCount, TimeSpan timeout)
        {
            var deadline = DateTimeOffset.UtcNow + timeout;
            while (UploadCount < expectedCount && DateTimeOffset.UtcNow < deadline)
            {
                await Task.Delay(50);
            }

            Assert.True(
                UploadCount >= expectedCount,
                $"Expected {expectedCount} upload(s), but observed {UploadCount}.");
        }

        public Task<AlbumAssetsResult> GetAlbumAssetsAsync(string albumName, CancellationToken cancellationToken) =>
            Task.FromResult(AlbumAssetsResult.Success(
                Enumerable.Range(1, UploadCount)
                    .Select(index => new AlbumAssetSummary($"asset-{index}", "photo.jpg"))
                    .ToArray()));

        public Task<DownloadAssetResult> DownloadAssetAsync(string assetId, string destinationPath, CancellationToken cancellationToken) =>
            Task.FromResult(DownloadAssetResult.Success());

        public Task<AlbumListResult> ListAlbumsAsync(CancellationToken cancellationToken) =>
            Task.FromResult(AlbumListResult.Success([]));

        public Task<UnassignedAssetsResult> GetUnassignedAssetsAsync(CancellationToken cancellationToken) =>
            Task.FromResult(UnassignedAssetsResult.Success([]));

        public Task<AlbumMembershipUpdateResult> AddAssetsToAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken) =>
            Task.FromResult(AlbumMembershipUpdateResult.Success());

        public Task<AlbumMembershipUpdateResult> RemoveAssetsFromAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken) =>
            Task.FromResult(AlbumMembershipUpdateResult.Success());

        public Task<TrashAssetsResult> TrashAssetsAsync(IReadOnlyList<string> assetIds, CancellationToken cancellationToken) =>
            Task.FromResult(TrashAssetsResult.Success());

        public Task<EnsureAlbumResult> EnsureAlbumAsync(string albumName, CancellationToken cancellationToken) =>
            Task.FromResult(EnsureAlbumResult.Success("album"));

        public Task<DeleteAlbumResult> DeleteAlbumAsync(string albumName, CancellationToken cancellationToken) =>
            Task.FromResult(DeleteAlbumResult.Success());

        public Task<RenameAlbumResult> RenameAlbumAsync(string oldAlbumName, string newAlbumName, CancellationToken cancellationToken) =>
            Task.FromResult(RenameAlbumResult.Success("album"));
    }

    private sealed class FailOnceDeletionService : ILocalFileDeletionService
    {
        private int _attemptCount;

        public int AttemptCount => Volatile.Read(ref _attemptCount);

        public void Delete(string filePath)
        {
            if (Interlocked.Increment(ref _attemptCount) == 1)
            {
                throw new IOException("Deletion intentionally failed.");
            }

            File.Delete(filePath);
        }
    }

    private sealed class TemporaryDirectory : IDisposable
    {
        public TemporaryDirectory()
        {
            Path = System.IO.Path.Combine(
                System.IO.Path.GetTempPath(),
                $"immich-folder-watch-worker-tests-{Guid.NewGuid():N}");
            Directory.CreateDirectory(Path);
        }

        public string Path { get; }

        public void Dispose()
        {
            Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
            Directory.Delete(Path, recursive: true);
        }
    }
}
