using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests
{
    [UnixFilePermissionsFact]
    public async Task Sync_WriteDeniedDirectorySkipsDownloadsAndRecoversWithoutRestart()
    {
        if (OperatingSystem.IsWindows()) return;

        using var directory = new TemporaryDirectory();
        var blockedDirectory = Directory.CreateDirectory(Path.Combine(directory.Path, "blocked")).FullName;
        var healthyDirectory = Directory.CreateDirectory(Path.Combine(directory.Path, "healthy")).FullName;
        var config = CreateConfig(blockedDirectory, WatchSourceSyncModes.Sync);
        config.Watch.Sources.Add(new WatchSourceSettings
        {
            Path = healthyDirectory,
            AlbumName = "Other",
            Extensions = [".jpg"],
            SyncMode = WatchSourceSyncModes.Sync,
        });
        var blockedAssets = Enumerable.Range(1, 68)
            .Select(index => new AlbumAssetSummary($"blocked-{index}", $"photo-{index}.jpg")).ToArray();
        var client = new RecordingAssetClient
        {
            AlbumAssetsHandler = album =>
            {
                if (album != "Camera") return AlbumAssetsResult.Success([new("healthy", "healthy.jpg")]);
                return AlbumAssetsResult.Success(blockedAssets);
            },
        };
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var status = new SyncStatusProvider();
        var realtime = new TriggeredRealtimeClient();
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync, sourceCount: 2);
        var mode = File.GetUnixFileMode(blockedDirectory);
        using var worker = CreateWorker(config, databasePath, client, syncStatusProvider: status,
            realtimeClient: realtime, workerLogger: logger);
        try
        {
            File.SetUnixFileMode(blockedDirectory, UnixFileMode.UserRead | UnixFileMode.UserExecute);
            // Verify the fixture really denies writes (privileged test runners can bypass mode bits).
            Assert.Throws<UnauthorizedAccessException>(() => File.WriteAllText(Path.Combine(blockedDirectory, "probe"), ""));
            await worker.StartAsync(CancellationToken.None);
            await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));

            Assert.Equal(new[] { "healthy" }, client.DownloadedAssets.ToArray());
            Assert.Contains("Cannot write downloads to folder", status.LastSyncErrorMessage);
            Assert.Contains(blockedDirectory, status.LastSyncErrorMessage);
            Assert.Contains("select the folder again", status.LastSyncErrorMessage);
            Assert.Empty(Directory.EnumerateFileSystemEntries(blockedDirectory));

            realtime.RequestPull();
            await WaitUntilAsync(() => logger.SyncPullFailureCount >= 2, TimeSpan.FromSeconds(8));
            Assert.Single(client.DownloadedAssets);
            Assert.NotNull(status.LastSyncErrorMessage);

            File.SetUnixFileMode(blockedDirectory, mode);
            realtime.RequestPull();
            await WaitUntilAsync(() => client.DownloadedAssets.Count == 69
                && status.CurrentPullSize == 0 && status.LastSyncErrorMessage is null, TimeSpan.FromSeconds(12));
            await worker.StopAsync(CancellationToken.None);

            Assert.Equal(68, Directory.GetFiles(blockedDirectory).Length);
            Assert.Single(Directory.GetFiles(healthyDirectory));
            Assert.Equal(0, client.UploadCount);
        }
        finally
        {
            File.SetUnixFileMode(blockedDirectory, mode);
            await worker.StopAsync(CancellationToken.None);
        }
    }

    [Fact]
    public async Task Sync_DirectoryCreationFailurePreservesPendingFilesAndDoesNotDownload()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        await File.WriteAllTextAsync(Path.Combine(watchDirectory, "Camera"), "existing local file");
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.Sync);
        config.Watch.Sources[0].AlbumName = "";
        var localPath = Path.Combine(watchDirectory, "keep.jpg");
        await File.WriteAllTextAsync(localPath, "previously downloaded media");
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var store = new SqliteSyncStateStore(databasePath);
        await store.UpsertAsync(new SyncStateEntry(
            SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey),
            watchDirectory, "keep.jpg", "removed-remotely", "", new FileInfo(localPath).Length,
            File.GetLastWriteTimeUtc(localPath), SyncTransferDirection.Download,
            SyncEntryStatus.Synchronized, DateTimeOffset.UtcNow.AddDays(-1)));
        var client = new RecordingAssetClient
        {
            RemoteAlbums = [new("album", "Camera")],
            RemoteAssets = [new("remote", "photo.jpg")],
        };
        var status = new SyncStatusProvider();
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var worker = CreateWorker(config, databasePath, client,
            syncStatusProvider: status, workerLogger: logger);
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);

        Assert.Empty(client.DownloadedAssets);
        Assert.NotNull(status.LastSyncErrorMessage);
        Assert.Null(status.LastSyncCompletedUtc);
        Assert.Equal("existing local file", await File.ReadAllTextAsync(Path.Combine(watchDirectory, "Camera")));
        Assert.Equal("previously downloaded media", await File.ReadAllTextAsync(localPath));
        Assert.Equal(SyncEntryStatus.Synchronized, Assert.Single(await GetEntriesAsync(config, databasePath)).Status);
        Assert.Equal(0, client.UploadCount);
    }

    private sealed class UnixFilePermissionsFactAttribute : FactAttribute
    {
        public UnixFilePermissionsFactAttribute()
        {
            if (OperatingSystem.IsWindows() || Environment.UserName == "root")
                Skip = "Requires Unix file mode enforcement for an unprivileged user.";
        }
    }
}
