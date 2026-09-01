using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class FolderWatchWorkerPersistenceTests
{
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
        RecordingAssetClient client) =>
        new(
            config,
            new AlwaysReadyChecker(),
            new UploadBatchQueue(),
            client,
            new SqliteSyncStateStore(databasePath),
            new SyncStatusProvider(),
            NullLogger<FolderWatchWorker>.Instance);

    private static AppConfig CreateConfig(string watchDirectory, string syncMode) =>
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
                    },
                ],
            },
        };

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

        public Task PingAsync(CancellationToken cancellationToken) => Task.CompletedTask;

        public Task<UploadAssetResult> UploadAssetAsync(
            UploadAssetRequest request,
            CancellationToken cancellationToken)
        {
            var count = Interlocked.Increment(ref _uploadCount);
            return Task.FromResult(UploadAssetResult.Success($"asset-{count}"));
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
