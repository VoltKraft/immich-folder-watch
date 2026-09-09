using System.Collections.Concurrent;
using System.Net;
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
    [InlineData(false)]
    [InlineData(true)]
    public async Task Sync_ReportsMissingAlbumAndPreservesLocalFilesUntilSelectedAlbumRecovers(bool previouslyDownloaded)
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.Sync);
        var remoteAssets = new[] { new AlbumAssetSummary("remote", "photo.jpg") };
        if (previouslyDownloaded)
        {
            var seedClient = new RecordingAssetClient { RemoteAssets = remoteAssets };
            var seedLogger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
            using var seedWorker = CreateWorker(config, databasePath, seedClient, workerLogger: seedLogger);
            await seedWorker.StartAsync(CancellationToken.None);
            await seedLogger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
            Assert.Single(seedClient.DownloadedAssets);
            await seedWorker.StopAsync(CancellationToken.None);
        }

        var albumMissing = 1;
        var client = new RecordingAssetClient
        {
            AlbumAssetsHandler = _ => Volatile.Read(ref albumMissing) == 1
                ? AlbumAssetsResult.Missing()
                : AlbumAssetsResult.Success(remoteAssets),
        };
        var status = new SyncStatusProvider();
        var realtime = new TriggeredRealtimeClient();
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var worker = CreateWorker(config, databasePath, client, workerLogger: logger,
            syncStatusProvider: status, realtimeClient: realtime);
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));

        Assert.Contains("configured Immich album 'Camera' does not exist", status.LastSyncErrorMessage);
        Assert.Contains("clear the album name", status.LastSyncErrorMessage);
        Assert.Empty(client.DownloadedAssets);
        Assert.Equal(0, client.UploadCount);
        Assert.Equal(previouslyDownloaded, File.Exists(Path.Combine(watchDirectory, "photo.jpg")));

        Interlocked.Exchange(ref albumMissing, 0);
        realtime.RequestPull();
        await WaitUntilAsync(
            () => status.LastSyncErrorMessage is null && status.CurrentPullSize == 0
                && (previouslyDownloaded || client.DownloadedAssets.Count == 1),
            TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);

        Assert.Equal("remote", await File.ReadAllTextAsync(Path.Combine(watchDirectory, "photo.jpg")));
        Assert.Equal(previouslyDownloaded ? 0 : 1, client.DownloadedAssets.Count);
        Assert.Equal(0, client.UploadCount);
    }

    [Fact]
    public async Task Sync_RetainsSourceListingFailureUntilSuccessfulEmptyRecoveryPull()
    {
        using var directory = new TemporaryDirectory();
        var firstDirectory = Directory.CreateDirectory(Path.Combine(directory.Path, "first")).FullName;
        var secondDirectory = Directory.CreateDirectory(Path.Combine(directory.Path, "second")).FullName;
        var failListing = 1;
        var client = new RecordingAssetClient
        {
            AlbumAssetsHandler = album => album == "Camera"
                ? Volatile.Read(ref failListing) == 1
                    ? AlbumAssetsResult.Failure(null, "Listing denied")
                    : AlbumAssetsResult.Success([])
                : AlbumAssetsResult.Success([new AlbumAssetSummary("remote", "remote.jpg")]),
        };
        var config = CreateConfig(firstDirectory, WatchSourceSyncModes.Sync);
        config.Watch.Sources.Add(new WatchSourceSettings
        {
            Path = secondDirectory,
            AlbumName = "Other",
            Extensions = [".jpg"],
            SyncMode = WatchSourceSyncModes.Sync,
        });
        var status = new SyncStatusProvider();
        var realtime = new TriggeredRealtimeClient();
        using var worker = CreateWorker(config, Path.Combine(directory.Path, "sync-state.db"), client,
            syncStatusProvider: status, realtimeClient: realtime);
        await worker.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => status.ProcessedFileCount == 1 && status.CurrentPullSize == 0,
            TimeSpan.FromSeconds(8));

        Assert.Equal("Listing denied", status.LastSyncErrorMessage);
        Interlocked.Exchange(ref failListing, 0);
        realtime.RequestPull();
        await WaitUntilAsync(() => status.LastSyncErrorMessage is null, TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);

        Assert.Equal(1, status.ProcessedFileCount);
        Assert.Equal(1, status.TotalFileCount);
        Assert.Single(client.DownloadedAssets);
    }

    [Theory]
    [InlineData(TransferOrders.NewestFirst, "new.jpg", "old.jpg")]
    [InlineData(TransferOrders.OldestFirst, "old.jpg", "new.jpg")]
    public async Task UploadAll_UsesGlobalTransferOrderAcrossBatches(string order, string first, string second)
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        foreach (var (name, year) in new[] { ("old.jpg", 2025), ("new.jpg", 2026) })
        {
            var path = Path.Combine(watchDirectory, name);
            await File.WriteAllTextAsync(path, name);
            File.SetLastWriteTimeUtc(path, new DateTime(year, 1, 1, 0, 0, 0, DateTimeKind.Utc));
        }

        var client = new RecordingAssetClient();
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadAll);
        config.Watch.TransferOrder = order;
        var status = new SyncStatusProvider();
        using var worker = CreateWorker(config, Path.Combine(directory.Path, "sync-state.db"), client,
            syncStatusProvider: status);
        await worker.StartAsync(CancellationToken.None);
        await client.WaitForUploadCountAsync(2, TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);

        Assert.Equal(new[] { first, second }, client.UploadedPaths.Select(Path.GetFileName).ToArray());
        Assert.Equal(2, status.ProcessedFileCount);
        Assert.Equal(2, status.TotalFileCount);
    }

    [Theory]
    [InlineData(TransferOrders.NewestFirst, "new", "old")]
    [InlineData(TransferOrders.OldestFirst, "old", "new")]
    public async Task Sync_DownloadsDatedAssetsInConfiguredOrderWithUnknownDatesLast(string order, string first, string second)
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var client = new RecordingAssetClient
        {
            RemoteAssets =
            [
                new AlbumAssetSummary("unknown", "unknown.jpg"),
                new AlbumAssetSummary("old", "old.jpg", new DateTimeOffset(2025, 1, 1, 0, 0, 0, TimeSpan.Zero)),
                new AlbumAssetSummary("new", "new.jpg", new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero)),
            ],
        };
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.Sync);
        config.Watch.TransferOrder = order;
        using var worker = CreateWorker(config, Path.Combine(directory.Path, "sync-state.db"), client);
        await worker.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => client.DownloadedAssets.Count >= 3, TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);

        Assert.Equal(new[] { first, second, "unknown" }, client.DownloadedAssets.ToArray());
    }

    [Theory]
    [InlineData(TransferOrders.NewestFirst, 2026, 2025)]
    [InlineData(TransferOrders.OldestFirst, 2025, 2026)]
    public async Task TransientFailure_DoesNotBlockNewFileBehindRetryAttempts(string order, int badYear, int goodYear)
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var badFilePath = Path.Combine(watchDirectory, "bad.jpg");
        var goodFilePath = Path.Combine(watchDirectory, "good.jpg");
        var firstUploadStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseFirstUpload = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var client = new RecordingAssetClient
        {
            UploadHandler = async (request, count, cancellationToken) =>
            {
                if (count == 1)
                {
                    Assert.Equal(badFilePath, request.FilePath);
                    firstUploadStarted.TrySetResult();
                    await releaseFirstUpload.Task.WaitAsync(cancellationToken);
                    return UploadAssetResult.Failure(null, "temporary network failure", canRetry: true);
                }

                return UploadAssetResult.Success($"asset-{count}");
            },
        };
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadNew);
        config.Watch.TransferOrder = order;
        var initialReconciliationLogger = new InitialReconciliationLogger();
        using var worker = CreateWorker(config, databasePath, client, workerLogger: initialReconciliationLogger);
        await worker.StartAsync(CancellationToken.None);
        await initialReconciliationLogger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));

        await File.WriteAllTextAsync(badFilePath, "bad");
        File.SetLastWriteTimeUtc(badFilePath, new DateTime(badYear, 1, 1, 0, 0, 0, DateTimeKind.Utc));
        await firstUploadStarted.Task.WaitAsync(TimeSpan.FromSeconds(8));
        await File.WriteAllTextAsync(goodFilePath, "good");
        File.SetLastWriteTimeUtc(goodFilePath, new DateTime(goodYear, 1, 1, 0, 0, 0, DateTimeKind.Utc));
        await Task.Delay(TimeSpan.FromSeconds(1));
        releaseFirstUpload.TrySetResult();

        await client.WaitForUploadCountAsync(3, TimeSpan.FromSeconds(8));

        Assert.Collection(
            client.UploadedPaths.Take(3),
            path => Assert.Equal(badFilePath, path),
            path => Assert.Equal(goodFilePath, path),
            path => Assert.Equal(badFilePath, path));
        await worker.StopAsync(CancellationToken.None);
    }

    [Fact]
    public async Task PermanentUploadFailure_IsNotQueuedAgain()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "unsupported.jpg");
        await File.WriteAllTextAsync(filePath, "unsupported");

        var client = new RecordingAssetClient
        {
            UploadHandler = (_, _, _) => Task.FromResult(
                UploadAssetResult.Failure(HttpStatusCode.BadRequest, "unsupported format")),
        };
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadAll);
        var lastSuccess = new DateTimeOffset(2025, 12, 3, 4, 5, 6, TimeSpan.Zero).AddTicks(1234);
        var store = new SqliteSyncStateStore(databasePath);
        var accountScope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        await store.RecordSuccessfulSyncAsync(accountScope, lastSuccess);
        var status = new SyncStatusProvider();
        using var worker = CreateWorker(config, databasePath, client, syncStatusProvider: status);
        await worker.StartAsync(CancellationToken.None);
        await client.WaitForUploadCountAsync(1, TimeSpan.FromSeconds(8));
        await Task.Delay(TimeSpan.FromSeconds(2));

        Assert.Equal(1, client.UploadCount);
        await worker.StopAsync(CancellationToken.None);
        Assert.Equal(lastSuccess, status.LastSyncCompletedUtc);
        Assert.Equal(lastSuccess, await store.GetLastSuccessfulSyncAsync(accountScope));
    }

    [Fact]
    public async Task TransientUploadFailure_StopsAfterConfiguredAttempts()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        await File.WriteAllTextAsync(Path.Combine(watchDirectory, "unavailable.jpg"), "unavailable");

        var client = new RecordingAssetClient
        {
            UploadHandler = (_, _, _) => Task.FromResult(
                UploadAssetResult.Failure(HttpStatusCode.ServiceUnavailable, "try later", canRetry: true)),
        };
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadAll);
        config.Retry.MaxAttempts = 3;
        config.Retry.BaseDelayMilliseconds = 1;
        var status = new SyncStatusProvider();
        using var worker = CreateWorker(config, databasePath, client, syncStatusProvider: status);
        await worker.StartAsync(CancellationToken.None);
        await client.WaitForUploadCountAsync(3, TimeSpan.FromSeconds(8));
        await Task.Delay(TimeSpan.FromSeconds(2));

        Assert.Equal(3, client.UploadCount);
        await worker.StopAsync(CancellationToken.None);
        Assert.Null(status.LastSyncCompletedUtc);
        Assert.Null(await GetLastSuccessfulSyncAsync(config, databasePath));
    }

    [Fact]
    public async Task Shutdown_RequeuesCanceledBatchAndDrainsAllUploadNewFiles()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);

        var cancellableUploadStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var client = new RecordingAssetClient
        {
            UploadHandler = async (_, count, cancellationToken) =>
            {
                if (count == 1)
                {
                    cancellableUploadStarted.TrySetResult();
                    await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
                }

                return UploadAssetResult.Success($"asset-{count}");
            },
        };
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadNew);
        var initialReconciliationLogger = new InitialReconciliationLogger();
        using var worker = CreateWorker(config, databasePath, client, workerLogger: initialReconciliationLogger);
        await worker.StartAsync(CancellationToken.None);
        await initialReconciliationLogger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await File.WriteAllTextAsync(Path.Combine(watchDirectory, "first.jpg"), "first");
        await File.WriteAllTextAsync(Path.Combine(watchDirectory, "second.jpg"), "second");
        await cancellableUploadStarted.Task.WaitAsync(TimeSpan.FromSeconds(8));

        await worker.StopAsync(CancellationToken.None);

        var entries = await GetEntriesAsync(config, databasePath);
        Assert.Equal(2, entries.Count);
        Assert.Equal(3, client.UploadCount);
    }

    [Fact]
    public async Task Shutdown_PromotesFreshUploadNewDebounceEntry()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient();
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadNew);
        var logger = new InitialReconciliationLogger();
        using var worker = CreateWorker(config, databasePath, client, workerLogger: logger);
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));

        await File.WriteAllTextAsync(Path.Combine(watchDirectory, "fresh.jpg"), "fresh");
        await logger.WaitForFileEventAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);

        Assert.Equal(1, client.UploadCount);
        Assert.Single(await GetEntriesAsync(config, databasePath));
    }

    [Fact]
    public async Task Shutdown_DoesNotLoopWhenFreshFileNeverBecomesReady()
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient();
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadNew);
        var logger = new InitialReconciliationLogger();
        using var worker = CreateWorker(
            config,
            databasePath,
            client,
            workerLogger: logger,
            fileReadinessChecker: new NeverReadyChecker());
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await File.WriteAllTextAsync(Path.Combine(watchDirectory, "locked.jpg"), "locked");
        await logger.WaitForFileEventAsync(TimeSpan.FromSeconds(8));

        await worker.StopAsync(CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(3));

        Assert.Equal(0, client.UploadCount);
    }

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
        var status = new SyncStatusProvider();
        using var worker = CreateWorker(
            config,
            databasePath,
            client,
            workerLogger: initialReconciliationLogger,
            syncStatusProvider: status);
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

        var lastSuccess = Assert.IsType<DateTimeOffset>(status.LastSyncCompletedUtc);
        Assert.Equal(lastSuccess, await GetLastSuccessfulSyncAsync(config, databasePath));
        var restoredStatus = new SyncStatusProvider();
        using var restartedWorker = CreateWorker(config, databasePath, client, syncStatusProvider: restoredStatus);
        await restartedWorker.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => restoredStatus.LastSyncCompletedUtc == lastSuccess, TimeSpan.FromSeconds(3));
        await restartedWorker.StopAsync(CancellationToken.None);
        Assert.Equal(lastSuccess, restoredStatus.LastSyncCompletedUtc);
        Assert.Equal(1, client.UploadCount);
        Assert.Empty(await GetEntriesAsync(config, databasePath));
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
            UploadHandler = async (_, count, cancellationToken) =>
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
        var lastSuccess = await RunUntilUploadCountAsync(initialConfig, databasePath, client, expectedCount: 1);

        var cleanupConfig = CreateConfig(
            watchDirectory,
            WatchSourceSyncModes.UploadAll,
            deleteAfterUpload: true);
        var status = new SyncStatusProvider();
        using var worker = CreateWorker(cleanupConfig, databasePath, client, syncStatusProvider: status);
        await worker.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => !File.Exists(filePath), TimeSpan.FromSeconds(3));

        Assert.Equal(1, client.UploadCount);
        Assert.Empty(await GetEntriesAsync(cleanupConfig, databasePath));
        await worker.StopAsync(CancellationToken.None);
        Assert.Equal(lastSuccess, status.LastSyncCompletedUtc);
        Assert.Equal(lastSuccess, await GetLastSuccessfulSyncAsync(cleanupConfig, databasePath));
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

    [Theory]
    [InlineData(0)]
    [InlineData(200)]
    public async Task RestartSkipsUnchangedFile_ThenUploadsSingleModification(int uploadDelayMilliseconds)
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Path.Combine(directory.Path, "watch");
        Directory.CreateDirectory(watchDirectory);
        var filePath = Path.Combine(watchDirectory, "photo.jpg");
        await File.WriteAllTextAsync(filePath, "first version");

        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var client = new RecordingAssetClient
        {
            UploadHandler = async (_, count, cancellationToken) =>
            {
                await Task.Delay(uploadDelayMilliseconds, cancellationToken);
                return UploadAssetResult.Success($"asset-{count}");
            },
        };
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadAll);

        var firstSuccess = await RunUntilUploadCountAsync(config, databasePath, client, expectedCount: 1);

        var syncConfig = CreateConfig(watchDirectory, WatchSourceSyncModes.Sync);
        var secondStatus = new SyncStatusProvider();
        using var secondWorker = CreateWorker(syncConfig, databasePath, client, syncStatusProvider: secondStatus);
        await secondWorker.StartAsync(CancellationToken.None);
        await Task.Delay(TimeSpan.FromMilliseconds(1500));
        Assert.Equal(1, client.UploadCount);
        await secondWorker.StopAsync(CancellationToken.None);
        Assert.Equal(1, client.UploadCount);
        Assert.Equal(firstSuccess, secondStatus.LastSyncCompletedUtc);
        Assert.Equal(firstSuccess, await GetLastSuccessfulSyncAsync(syncConfig, databasePath));

        await File.WriteAllTextAsync(filePath, "second version with a different size");
        var thirdStatus = new SyncStatusProvider();
        using var thirdWorker = CreateWorker(syncConfig, databasePath, client, syncStatusProvider: thirdStatus);
        await thirdWorker.StartAsync(CancellationToken.None);
        await client.WaitForUploadCountAsync(2, TimeSpan.FromSeconds(8));
        // The client counts attempts before the worker persists success. Stopping
        // earlier can cancel that work and replay the upload during shutdown.
        await WaitUntilAsync(
            () => thirdStatus.LastSyncCompletedUtc > firstSuccess,
            TimeSpan.FromSeconds(8));
        Assert.Equal(2, client.UploadCount);
        await thirdWorker.StopAsync(CancellationToken.None);
        Assert.Equal(2, client.UploadCount);
        var secondSuccess = Assert.IsType<DateTimeOffset>(thirdStatus.LastSyncCompletedUtc);
        Assert.True(secondSuccess > firstSuccess);
        Assert.Equal(secondSuccess, await GetLastSuccessfulSyncAsync(syncConfig, databasePath));

        var fourthStatus = new SyncStatusProvider();
        using var fourthWorker = CreateWorker(syncConfig, databasePath, client, syncStatusProvider: fourthStatus);
        await fourthWorker.StartAsync(CancellationToken.None);
        await Task.Delay(TimeSpan.FromMilliseconds(1500));
        Assert.Equal(2, client.UploadCount);
        await fourthWorker.StopAsync(CancellationToken.None);
        Assert.Equal(2, client.UploadCount);
        Assert.Equal(secondSuccess, fourthStatus.LastSyncCompletedUtc);

        var store = new SqliteSyncStateStore(databasePath);
        var scope = SyncAccountScope.Create(syncConfig.Immich.ServerApiUrl, syncConfig.Immich.ApiKey);
        var entry = Assert.Single(await store.GetSourceEntriesAsync(scope, watchDirectory));
        Assert.Equal("asset-2", entry.AssetId);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Restart_RestoresDownloadCompletionWithoutAdvancingForKnownAssetsOrEmptyPull(bool emptyAlbum)
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.Sync);
        var client = new RecordingAssetClient
        {
            RemoteAssets = [new AlbumAssetSummary("remote-photo", "photo.jpg")],
        };
        var firstStatus = new SyncStatusProvider();
        using (var firstWorker = CreateWorker(config, databasePath, client, syncStatusProvider: firstStatus))
        {
            await firstWorker.StartAsync(CancellationToken.None);
            await WaitUntilAsync(() => firstStatus.LastSyncCompletedUtc is not null, TimeSpan.FromSeconds(8));
            await firstWorker.StopAsync(CancellationToken.None);
        }

        var lastSuccess = Assert.IsType<DateTimeOffset>(firstStatus.LastSyncCompletedUtc);
        Assert.Single(client.DownloadedAssets);
        Assert.Equal(0, client.UploadCount);
        Assert.Equal(lastSuccess, await GetLastSuccessfulSyncAsync(config, databasePath));

        var listingObserved = new TaskCompletionSource<DateTimeOffset?>(TaskCreationOptions.RunContinuationsAsynchronously);
        var restoredStatus = new SyncStatusProvider();
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        var secondClient = new RecordingAssetClient
        {
            AlbumAssetsHandler = _ =>
            {
                listingObserved.TrySetResult(restoredStatus.LastSyncCompletedUtc);
                return AlbumAssetsResult.Success(emptyAlbum ? [] : client.RemoteAssets!);
            },
        };
        using var secondWorker = CreateWorker(config, databasePath, secondClient,
            workerLogger: logger, syncStatusProvider: restoredStatus);
        await secondWorker.StartAsync(CancellationToken.None);
        Assert.Equal(lastSuccess, await listingObserved.Task.WaitAsync(TimeSpan.FromSeconds(3)));
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(3));
        await secondWorker.StopAsync(CancellationToken.None);

        Assert.Equal(lastSuccess, restoredStatus.LastSyncCompletedUtc);
        Assert.Equal(lastSuccess, await GetLastSuccessfulSyncAsync(config, databasePath));
        Assert.Empty(secondClient.DownloadedAssets);
        Assert.Equal(0, secondClient.UploadCount);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Restart_WithChangedAccountClearsPreviousAccountCompletion(bool changeServer)
    {
        using var directory = new TemporaryDirectory();
        var watchDirectory = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var config = CreateConfig(watchDirectory, WatchSourceSyncModes.UploadNew);
        var lastSuccess = new DateTimeOffset(2025, 10, 9, 8, 7, 6, TimeSpan.Zero);
        var store = new SqliteSyncStateStore(databasePath);
        var originalScope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        await store.RecordSuccessfulSyncAsync(originalScope, lastSuccess);
        var status = new SyncStatusProvider();
        var client = new RecordingAssetClient();
        var firstLogger = new InitialReconciliationLogger();
        using (var firstWorker = CreateWorker(config, databasePath, client,
            workerLogger: firstLogger, syncStatusProvider: status))
        {
            await firstWorker.StartAsync(CancellationToken.None);
            await firstLogger.WaitUntilReadyAsync(TimeSpan.FromSeconds(3));
            Assert.Equal(lastSuccess, status.LastSyncCompletedUtc);
            await firstWorker.StopAsync(CancellationToken.None);
        }

        if (changeServer)
        {
            config.Immich.ServerApiUrl = "https://other-immich.example/api";
        }
        else
        {
            config.Immich.ApiKey = "other-test-key";
        }

        var secondLogger = new InitialReconciliationLogger();
        using var secondWorker = CreateWorker(config, databasePath, client,
            workerLogger: secondLogger, syncStatusProvider: status);
        await secondWorker.StartAsync(CancellationToken.None);
        await secondLogger.WaitUntilReadyAsync(TimeSpan.FromSeconds(3));
        await secondWorker.StopAsync(CancellationToken.None);

        Assert.Null(status.LastSyncCompletedUtc);
        Assert.Null(await GetLastSuccessfulSyncAsync(config, databasePath));
        Assert.Equal(lastSuccess, await store.GetLastSuccessfulSyncAsync(originalScope));
        Assert.Equal(0, client.UploadCount);
        Assert.Empty(client.DownloadedAssets);
    }

    private static async Task<DateTimeOffset> RunUntilUploadCountAsync(
        AppConfig config,
        string databasePath,
        RecordingAssetClient client,
        int expectedCount)
    {
        var status = new SyncStatusProvider();
        using var worker = CreateWorker(config, databasePath, client, syncStatusProvider: status);
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
        await WaitUntilAsync(() => status.LastSyncCompletedUtc.HasValue, TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);
        Assert.Equal(expectedCount, client.UploadCount);
        var lastSuccess = Assert.IsType<DateTimeOffset>(status.LastSyncCompletedUtc);
        Assert.Equal(lastSuccess, await store.GetLastSuccessfulSyncAsync(scope));
        return lastSuccess;
    }

    private static Task<DateTimeOffset?> GetLastSuccessfulSyncAsync(AppConfig config, string databasePath)
    {
        var scope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        return new SqliteSyncStateStore(databasePath).GetLastSuccessfulSyncAsync(scope);
    }

    private static FolderWatchWorker CreateWorker(
        AppConfig config,
        string databasePath,
        RecordingAssetClient client,
        ILocalFileDeletionService? localFileDeletionService = null,
        ILogger<FolderWatchWorker>? workerLogger = null,
        IFileReadinessChecker? fileReadinessChecker = null,
        SyncStatusProvider? syncStatusProvider = null,
        IImmichRealtimeClient? realtimeClient = null) =>
        new(
            config,
            fileReadinessChecker ?? new AlwaysReadyChecker(),
            localFileDeletionService ?? new LocalFileDeletionService(),
            new UploadBatchQueue(),
            client,
            new SqliteSyncStateStore(databasePath),
            syncStatusProvider ?? new SyncStatusProvider(),
            workerLogger ?? NullLogger<FolderWatchWorker>.Instance,
            realtimeClient);

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
        private readonly string _reconciliationMessagePrefix;

        private readonly TaskCompletionSource _ready = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource _fileEvent = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _reconciliationCount;

        public InitialReconciliationLogger(string syncMode = WatchSourceSyncModes.UploadNew)
        {
            _reconciliationMessagePrefix = $"Persistent reconciliation for {syncMode}";
        }

        public Task WaitUntilReadyAsync(TimeSpan timeout) => _ready.Task.WaitAsync(timeout);

        public Task WaitForFileEventAsync(TimeSpan timeout) => _fileEvent.Task.WaitAsync(timeout);

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
            var message = formatter(state, exception);
            if (logLevel == LogLevel.Debug
                && message.StartsWith("File event captured", StringComparison.Ordinal))
            {
                _fileEvent.TrySetResult();
            }

            if (logLevel != LogLevel.Information
                || !message.StartsWith(_reconciliationMessagePrefix, StringComparison.Ordinal))
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

    private sealed class NeverReadyChecker : IFileReadinessChecker
    {
        public Task<bool> WaitUntilReadyAsync(
            string filePath,
            TimeSpan timeout,
            CancellationToken cancellationToken) => Task.FromResult(false);
    }

    private sealed class RecordingAssetClient : IImmichAssetClient
    {
        private int _uploadCount;

        public ConcurrentQueue<string> DownloadedAssets { get; } = new();

        public IReadOnlyList<AlbumAssetSummary>? RemoteAssets { get; init; }

        public Func<string, AlbumAssetsResult>? AlbumAssetsHandler { get; init; }

        private readonly ConcurrentQueue<string> _uploadedPaths = new();

        public int UploadCount => Volatile.Read(ref _uploadCount);

        public IReadOnlyList<string> UploadedPaths => _uploadedPaths.ToArray();

        public bool FailUploads { get; init; }

        public Func<UploadAssetRequest, int, CancellationToken, Task<UploadAssetResult>>? UploadHandler { get; init; }

        public Task PingAsync(CancellationToken cancellationToken) => Task.CompletedTask;

        public async Task<UploadAssetResult> UploadAssetAsync(
            UploadAssetRequest request,
            CancellationToken cancellationToken)
        {
            _uploadedPaths.Enqueue(request.FilePath);
            var count = Interlocked.Increment(ref _uploadCount);
            if (UploadHandler is not null)
            {
                return await UploadHandler(request, count, cancellationToken);
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
            Task.FromResult(AlbumAssetsHandler?.Invoke(albumName) ?? AlbumAssetsResult.Success(
                RemoteAssets ?? Enumerable.Range(1, UploadCount)
                    .Select(index => new AlbumAssetSummary($"asset-{index}", "photo.jpg"))
                    .ToArray()));

        public async Task<DownloadAssetResult> DownloadAssetAsync(string assetId, string destinationPath, CancellationToken cancellationToken)
        {
            await File.WriteAllTextAsync(destinationPath, assetId, cancellationToken);
            DownloadedAssets.Enqueue(assetId);
            return DownloadAssetResult.Success();
        }

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

    private sealed class TriggeredRealtimeClient : IImmichRealtimeClient
    {
        public event EventHandler? RemoteChangeDetected;

        public void RequestPull() => RemoteChangeDetected?.Invoke(this, EventArgs.Empty);

        public Task StartAsync(CancellationToken cancellationToken) => Task.CompletedTask;

        public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
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
