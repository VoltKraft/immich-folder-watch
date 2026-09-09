using System.Security.Cryptography;
using Microsoft.Extensions.Logging;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests
{
    private static readonly DateTimeOffset OriginalCreated = new(2004, 2, 4, 6, 8, 10, TimeSpan.Zero);
    private static readonly AlbumAssetSummary DatedAsset = new("remote", "photo.jpg", OriginalCreated.AddDays(2), OriginalCreated);

    [Fact]
    public async Task Download_RestoresOriginalTimestampsAndRestartDoesNotUpload()
    {
        using var directory = new TemporaryDirectory();
        var root = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var database = Path.Combine(directory.Path, "state.db");
        var config = CreateConfig(root, WatchSourceSyncModes.Sync);
        var client = new RecordingAssetClient { RemoteAssets = [DatedAsset] };
        for (var run = 0; run < 2; run++)
        {
            var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
            using var worker = CreateWorker(config, database, client, workerLogger: logger);
            await worker.StartAsync(CancellationToken.None);
            await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
            await worker.StopAsync(CancellationToken.None);
            AssertRestoredDates(Path.Combine(root, "photo.jpg"));
        }
        Assert.Single(client.DownloadedAssets);
        Assert.Equal(0, client.UploadCount);
        Assert.Equal("remote", await File.ReadAllTextAsync(Path.Combine(root, "photo.jpg")));
    }

    [Fact]
    public async Task TimestampRepair_UpdatesKnownDownloadWithoutAdvancingTransferHistory()
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        var client = new RecordingAssetClient { RemoteAssets = [DatedAsset] };
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var worker = CreateWorker(seed.Config, seed.Store.DatabasePath, client, workerLogger: logger);
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);
        AssertRestoredDates(seed.Path);
        var updated = Assert.Single(await GetEntriesAsync(seed.Config, seed.Store.DatabasePath));
        Assert.Equal(seed.Entry.LastSynchronizedAtUtc, updated.LastSynchronizedAtUtc);
        Assert.Equal(seed.Entry.LastSynchronizedAtUtc, await seed.Store.GetLastSuccessfulSyncAsync(seed.Entry.AccountScope));
        Assert.Empty(await seed.Store.GetTimestampRepairsAsync(seed.Entry.AccountScope, seed.Entry.SourcePath));
        Assert.Empty(client.DownloadedAssets);
        Assert.Equal(0, client.UploadCount);
    }

    [Theory]
    [InlineData("uploaded")]
    [InlineData("modified")]
    [InlineData("unmapped")]
    public async Task TimestampRepair_DoesNotRewriteOtherLocalFiles(string kind)
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        if (kind == "uploaded") await seed.Store.UpsertAsync(seed.Entry with { Direction = SyncTransferDirection.Upload });
        if (kind == "unmapped") await seed.Store.DeleteAsync(seed.Entry.AccountScope, seed.Entry.SourcePath, seed.Entry.RelativePath);
        if (kind == "modified")
        {
            await File.WriteAllTextAsync(seed.Path, "edited");
            File.SetLastWriteTimeUtc(seed.Path, OriginalCreated.AddYears(1).UtcDateTime);
        }
        var before = File.GetLastWriteTimeUtc(seed.Path);
        var client = new RecordingAssetClient { RemoteAssets = [DatedAsset] };
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var worker = CreateWorker(seed.Config, seed.Store.DatabasePath, client, workerLogger: logger);
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);
        Assert.Equal(before, File.GetLastWriteTimeUtc(seed.Path));
        Assert.Equal(kind == "modified" ? "edited" : "remote", await File.ReadAllTextAsync(seed.Path));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task TimestampRepair_RecoversInterruptedOperationBeforeUploadReconciliation(bool metadataAlreadyChanged)
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        var desired = DownloadedFileTimestamps.GetDesired(DatedAsset)!;
        var hash = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(seed.Path)));
        await seed.Store.SaveTimestampRepairAsync(new(seed.Entry, desired.CreationTimeUtc, desired.LastWriteTimeUtc, hash));
        if (metadataAlreadyChanged) DownloadedFileTimestamps.Apply(seed.Path, desired);
        var client = new RecordingAssetClient { RemoteAssets = [DatedAsset] };
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var worker = CreateWorker(seed.Config, seed.Store.DatabasePath, client, workerLogger: logger);
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);
        AssertRestoredDates(seed.Path);
        Assert.Equal(0, client.UploadCount);
        Assert.Empty(client.DownloadedAssets);
        Assert.Empty(await seed.Store.GetTimestampRepairsAsync(seed.Entry.AccountScope, seed.Entry.SourcePath));
    }

    [Fact]
    public async Task TimestampRepair_RecoveryPreservesEditEvenWithMatchingSizeAndTimestamp()
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        var desired = DownloadedFileTimestamps.GetDesired(DatedAsset)!;
        var hash = Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(seed.Path)));
        await seed.Store.SaveTimestampRepairAsync(new(seed.Entry, desired.CreationTimeUtc, desired.LastWriteTimeUtc, hash));
        await File.WriteAllTextAsync(seed.Path, "edited");
        File.SetLastWriteTimeUtc(seed.Path, desired.LastWriteTimeUtc.UtcDateTime);
        var client = new RecordingAssetClient { RemoteAssets = [DatedAsset] };
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var worker = CreateWorker(seed.Config, seed.Store.DatabasePath, client, workerLogger: logger);
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);
        Assert.Equal("edited", await File.ReadAllTextAsync(seed.Path));
        Assert.Equal(1, client.UploadCount);
        Assert.Empty(await seed.Store.GetTimestampRepairsAsync(seed.Entry.AccountScope, seed.Entry.SourcePath));
    }

    [Fact]
    public async Task TimestampRepair_DatabaseFailurePausesWithoutUploadAndNextStartRecovers()
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        var client = new RecordingAssetClient { RemoteAssets = [DatedAsset] };
        var status = new SyncStatusProvider();
        using (var worker = CreateWorker(seed.Config, seed.Store.DatabasePath, client,
            syncStatusProvider: status, stateStore: new FailingTimestampCompletionStore(seed.Store)))
        {
            await worker.StartAsync(CancellationToken.None);
            await worker.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(8));
            await worker.StopAsync(CancellationToken.None);
        }
        Assert.Contains("Timestamp correction", status.LastSyncErrorMessage);
        Assert.Equal(0, client.UploadCount);
        Assert.Single(await seed.Store.GetTimestampRepairsAsync(seed.Entry.AccountScope, seed.Entry.SourcePath));
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var recovered = CreateWorker(seed.Config, seed.Store.DatabasePath, client, workerLogger: logger);
        await recovered.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await recovered.StopAsync(CancellationToken.None);
        AssertRestoredDates(seed.Path);
        Assert.Equal(0, client.UploadCount);
    }

    [Fact]
    public async Task TimestampRepair_CancelDuringStateLoadingDoesNotFlushCapturedChanges()
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        var store = new FailingTimestampCompletionStore(seed.Store, pauseLoad: true);
        var client = new RecordingAssetClient { RemoteAssets = [DatedAsset] };
        var logger = new CapturedFileEventLogger();
        using var worker = CreateWorker(seed.Config, seed.Store.DatabasePath, client, workerLogger: logger, stateStore: store);
        await worker.StartAsync(CancellationToken.None);
        await store.LoadStarted.Task.WaitAsync(TimeSpan.FromSeconds(8));
        await File.WriteAllTextAsync(Path.Combine(Path.GetDirectoryName(seed.Path)!, "new.jpg"), "local");
        await logger.Captured.Task.WaitAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);
        Assert.Equal(0, client.UploadCount);
    }

    private sealed class CapturedFileEventLogger : ILogger<FolderWatchWorker>
    {
        public TaskCompletionSource Captured { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel level) => true;
        public void Log<TState>(LogLevel level, EventId id, TState state, Exception? error, Func<TState, Exception?, string> formatter)
        {
            if (formatter(state, error).StartsWith("File event captured", StringComparison.Ordinal)) Captured.TrySetResult();
        }
    }

    private static void AssertRestoredDates(string path)
    {
        var expected = DownloadedFileTimestamps.GetDesired(DatedAsset)!;
        Assert.Equal(expected.LastWriteTimeUtc.UtcDateTime, File.GetLastWriteTimeUtc(path));
        if (OperatingSystem.IsWindows()) Assert.Equal(expected.CreationTimeUtc.UtcDateTime, File.GetCreationTimeUtc(path));
    }

    private static async Task<(AppConfig Config, SqliteSyncStateStore Store, SyncStateEntry Entry, string Path)> SeedTimestampFileAsync(string directory)
    {
        var root = Directory.CreateDirectory(Path.Combine(directory, "watch")).FullName;
        var path = Path.Combine(root, "photo.jpg");
        await File.WriteAllTextAsync(path, "remote");
        var config = CreateConfig(root, WatchSourceSyncModes.Sync);
        var store = new SqliteSyncStateStore(Path.Combine(directory, "state.db"));
        var entry = new SyncStateEntry(SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey),
            root, "photo.jpg", "remote", "Camera", new FileInfo(path).Length,
            File.GetLastWriteTimeUtc(path), SyncTransferDirection.Download, SyncEntryStatus.Synchronized, OriginalCreated.AddYears(10));
        await store.UpsertAsync(entry);
        await store.RecordSuccessfulSyncAsync(entry.AccountScope, entry.LastSynchronizedAtUtc);
        return (config, store, entry, path);
    }

    private sealed class FailingTimestampCompletionStore(ISyncStateStore inner, bool pauseLoad = false) : ISyncStateStore
    {
        public string DatabasePath => inner.DatabasePath;
        public Task InitializeAsync(CancellationToken ct = default) => inner.InitializeAsync(ct);
        public Task<DateTimeOffset?> GetLastSuccessfulSyncAsync(string account, CancellationToken ct = default) => inner.GetLastSuccessfulSyncAsync(account, ct);
        public Task RecordSuccessfulSyncAsync(string account, DateTimeOffset date, CancellationToken ct = default) => inner.RecordSuccessfulSyncAsync(account, date, ct);
        public Task<SyncStateEntry?> GetAsync(string account, string source, string relative, CancellationToken ct = default) => inner.GetAsync(account, source, relative, ct);
        public TaskCompletionSource LoadStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public async Task<IReadOnlyList<SyncStateEntry>> GetSourceEntriesAsync(string account, string source, CancellationToken ct = default)
        {
            if (pauseLoad)
            {
                LoadStarted.TrySetResult();
                await Task.Delay(Timeout.Infinite, ct);
            }
            return await inner.GetSourceEntriesAsync(account, source, ct);
        }
        public Task UpsertAsync(SyncStateEntry entry, CancellationToken ct = default) => inner.UpsertAsync(entry, ct);
        public Task<bool> DeleteAsync(string account, string source, string relative, CancellationToken ct = default) => inner.DeleteAsync(account, source, relative, ct);
        public Task<int> DeleteExpiredTombstonesAsync(DateTimeOffset date, CancellationToken ct = default) => inner.DeleteExpiredTombstonesAsync(date, ct);
        public Task SaveTimestampRepairAsync(SyncTimestampRepair repair, CancellationToken ct = default) => inner.SaveTimestampRepairAsync(repair, ct);
        public Task<IReadOnlyList<SyncTimestampRepair>> GetTimestampRepairsAsync(string account, string source, CancellationToken ct = default) => inner.GetTimestampRepairsAsync(account, source, ct);
        public Task CompleteTimestampRepairAsync(SyncTimestampRepair repair, SyncStateEntry? updated, CancellationToken ct = default) => throw new IOException("Simulated timestamp journal commit failure.");
    }
}
