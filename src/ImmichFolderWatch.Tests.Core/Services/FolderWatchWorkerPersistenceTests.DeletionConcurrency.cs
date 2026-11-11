using System.Collections;
using System.Reflection;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Sync_ConcurrentDeleteCallbacksTrashOnceAndAllowRetryAfterPersistenceFailure(bool failFirstWrite)
    {
        using var directory = new TemporaryDirectory();
        var root = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var databasePath = Path.Combine(directory.Path, "state.db");
        var config = CreateConfig(root, WatchSourceSyncModes.Sync);
        var store = new PausedDeletionStore(new SqliteSyncStateStore(databasePath), failFirstWrite);
        var seed = new SyncStateEntry(
            SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey),
            root, "photo.jpg", "remote", "Camera", 6, DateTime.UtcNow,
            SyncTransferDirection.Download, SyncEntryStatus.Synchronized, DateTimeOffset.UtcNow);
        await store.UpsertAsync(seed);
        var client = new RecordingAssetClient();
        using var worker = CreateWorker(config, databasePath, client, stateStore: store);
        InitializeSecurityWorker(worker);
        const BindingFlags flags = BindingFlags.NonPublic | BindingFlags.Instance;
        await (Task)typeof(FolderWatchWorker).GetMethod("LoadPersistedStateAsync", flags)!
            .Invoke(worker, [CancellationToken.None])!;
        var context = ((IEnumerable)typeof(FolderWatchWorker).GetField("_sources", flags)!
            .GetValue(worker)!).Cast<object>().Single();
        var handler = typeof(FolderWatchWorker).GetMethod("HandleDeleteInSyncAsync", flags)!;
        Task DeleteAsync() => (Task)handler.Invoke(worker, [context, Path.Combine(root, "photo.jpg")])!;
        Task PollAsync() => (Task)typeof(FolderWatchWorker).GetMethod("PollDirectoriesForChangesAsync", flags)!
            .Invoke(worker, [CancellationToken.None])!;

        await File.WriteAllTextAsync(Path.Combine(root, "photo.jpg"), "remote");
        await PollAsync();
        File.Delete(Path.Combine(root, "photo.jpg"));

        var first = DeleteAsync();
        Task? duplicate = null;
        try
        {
            await store.WriteStarted.Task.WaitAsync(TimeSpan.FromSeconds(8));
            // Reproduce polling arriving while the watcher awaits durable state.
            duplicate = PollAsync();
        }
        finally
        {
            store.ReleaseWrite.TrySetResult();
            await first;
            if (duplicate is not null) await duplicate;
        }

        if (failFirstWrite)
        {
            Assert.Empty(client.TrashedAssets);
            Assert.Equal(SyncEntryStatus.Synchronized, (await store.GetAsync(seed.AccountScope, root, seed.RelativePath))!.Status);
            await PollAsync();
        }

        Assert.Equal(new[] { "remote" }, client.TrashedAssets.ToArray());
        var tombstone = Assert.Single(await GetEntriesAsync(config, databasePath));
        Assert.Equal(SyncEntryStatus.Tombstone, tombstone.Status);
        Assert.Equal("remote", tombstone.AssetId);
    }

    private sealed class PausedDeletionStore(ISyncStateStore inner, bool failFirstWrite) : ISyncStateStore
    {
        private int _tombstoneWrites;
        public TaskCompletionSource WriteStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource ReleaseWrite { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public string DatabasePath => inner.DatabasePath;

        public async Task UpsertAsync(SyncStateEntry entry, CancellationToken ct = default)
        {
            if (entry.Status == SyncEntryStatus.Tombstone && Interlocked.Increment(ref _tombstoneWrites) == 1)
            {
                WriteStarted.TrySetResult();
                await ReleaseWrite.Task.WaitAsync(ct);
                if (failFirstWrite) throw new IOException("Simulated tombstone persistence failure.");
            }
            await inner.UpsertAsync(entry, ct);
        }

        public Task InitializeAsync(CancellationToken ct = default) => inner.InitializeAsync(ct);
        public Task<DateTimeOffset?> GetLastSuccessfulSyncAsync(string account, CancellationToken ct = default) => inner.GetLastSuccessfulSyncAsync(account, ct);
        public Task RecordSuccessfulSyncAsync(string account, DateTimeOffset date, CancellationToken ct = default) => inner.RecordSuccessfulSyncAsync(account, date, ct);
        public Task<SyncStateEntry?> GetAsync(string account, string source, string relative, CancellationToken ct = default) => inner.GetAsync(account, source, relative, ct);
        public Task<IReadOnlyList<SyncStateEntry>> GetSourceEntriesAsync(string account, string source, CancellationToken ct = default) => inner.GetSourceEntriesAsync(account, source, ct);
        public Task<bool> DeleteAsync(string account, string source, string relative, CancellationToken ct = default) => inner.DeleteAsync(account, source, relative, ct);
        public Task<int> DeleteExpiredTombstonesAsync(DateTimeOffset date, CancellationToken ct = default) => inner.DeleteExpiredTombstonesAsync(date, ct);
        public Task SaveTimestampRepairAsync(SyncTimestampRepair repair, CancellationToken ct = default) => inner.SaveTimestampRepairAsync(repair, ct);
        public Task<IReadOnlyList<SyncTimestampRepair>> GetTimestampRepairsAsync(string account, string source, CancellationToken ct = default) => inner.GetTimestampRepairsAsync(account, source, ct);
        public Task CompleteTimestampRepairAsync(SyncTimestampRepair repair, SyncStateEntry? updated, CancellationToken ct = default) => inner.CompleteTimestampRepairAsync(repair, updated, ct);
    }
}
