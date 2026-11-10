using System.Collections;
using System.Reflection;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests
{
    [Fact]
    public async Task DeleteAfterUpload_RestartDoesNotDeleteSameFingerprintReplacementWithoutNewUpload()
    {
        using var directory = new TemporaryDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var path = Path.Combine(watch, "photo.jpg");
        await File.WriteAllTextAsync(path, "original");
        var db = Path.Combine(directory.Path, "state.db");
        var config = CreateConfig(watch, WatchSourceSyncModes.UploadAll);
        await RunUntilUploadCountAsync(config, db, new RecordingAssetClient(), 1);
        var modified = File.GetLastWriteTimeUtc(path);
        File.Move(path, path + ".old");
        await File.WriteAllTextAsync(path, "replaced");
        File.SetLastWriteTimeUtc(path, modified);
        config.Watch.Sources[0].DeleteAfterUpload = true;
        var client = new RecordingAssetClient { FailUploads = true };
        using var worker = CreateWorker(config, db, client);
        await worker.StartAsync(default);
        await client.WaitForUploadCountAsync(1, TimeSpan.FromSeconds(8));
        await worker.StopAsync(default);
        Assert.Equal("replaced", await File.ReadAllTextAsync(path));
        Assert.Single(await GetEntriesAsync(config, db));
    }

    [Fact]
    public async Task AdvisoryDeleteAfterRootReplacementDoesNotTrashPinnedFile()
    {
        using var directory = new TemporaryDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var path = Path.Combine(watch, "photo.jpg");
        await File.WriteAllTextAsync(path, "authorized");
        var db = Path.Combine(directory.Path, "state.db");
        var config = CreateConfig(watch, WatchSourceSyncModes.Sync);
        var client = new RecordingAssetClient();
        using var worker = CreateWorker(config, db, client);
        InitializeSecurityWorker(worker);
        var context = GetOnlySecurityContext(worker);
        var paths = (System.Collections.Concurrent.ConcurrentDictionary<string, string>)typeof(FolderWatchWorker).GetField("_pathToAssetId", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(worker)!;
        paths[path] = "asset";
        var moved = Path.Combine(directory.Path, "moved");
        var renamed = false;
        try { Directory.Move(watch, moved); renamed = true; }
        catch (IOException) when (OperatingSystem.IsWindows()) { }
        if (renamed) Directory.CreateDirectory(watch);
        await InvokeSecurityMethod(worker, "HandleDeleteInSyncAsync", context, path);
        Assert.Empty(client.TrashedAssets);
        Assert.True(File.Exists(Path.Combine(renamed ? moved : watch, "photo.jpg")));
    }

    [Fact]
    public async Task InternalPathsNeverQueueUploadsOrAlbumMutations()
    {
        using var directory = new TemporaryDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var internalDirectory = Directory.CreateDirectory(Path.Combine(watch, ".ifw-internal-test")).FullName;
        var path = Path.Combine(internalDirectory, "payload.jpg");
        await File.WriteAllTextAsync(path, "internal");
        var config = CreateConfig(watch, WatchSourceSyncModes.Sync);
        config.Watch.Sources[0].AlbumName = "";
        var client = new RecordingAssetClient();
        using var worker = CreateWorker(config, Path.Combine(directory.Path, "state.db"), client);
        InitializeSecurityWorker(worker);
        typeof(FolderWatchWorker).GetMethod("OnFileEvent", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(worker, [GetOnlySecurityContext(worker), path]);
        await InvokeAlbumHandler(worker, "HandleSubdirCreatedAsync", internalDirectory);
        await InvokeAlbumHandler(worker, "HandleSubdirDeletedAsync", internalDirectory);
        Assert.Equal(0, (int)typeof(FolderWatchWorker).GetMethod("GetPendingUploadCount", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(worker, null)!);
        Assert.Empty(client.MutatedAlbums);
    }

    [Fact]
    public async Task TimestampRepairRemainsAnchoredWhenRootChangesAfterContentDigest()
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        var watch = Path.GetDirectoryName(seed.Path)!;
        var moved = Path.Combine(directory.Path, "moved");
        var outside = Directory.CreateDirectory(Path.Combine(directory.Path, "outside")).FullName;
        var privatePath = Path.Combine(outside, "photo.jpg");
        await File.WriteAllTextAsync(privatePath, "remote");
        var privateTime = File.GetLastWriteTimeUtc(privatePath);
        var renamed = false;
        var store = new PathMutationStore(seed.Store)
        {
            BeforeSaveRepair = () =>
            {
                try { Directory.Move(watch, moved); renamed = true; }
                catch (IOException) when (OperatingSystem.IsWindows()) { }
                if (renamed) Directory.CreateSymbolicLink(watch, outside);
            },
        };
        using var worker = CreateWorker(seed.Config, store.DatabasePath, new RecordingAssetClient(), stateStore: store);
        InitializeSecurityWorker(worker);
        await InvokeSecurityMethod(worker, "LoadPersistedStateAsync", CancellationToken.None);
        await InvokeSecurityMethod(worker, "CorrectDownloadedTimestampsAsync", GetOnlySecurityContext(worker), seed.Path, DatedAsset, seed.Entry, CancellationToken.None);
        AssertRestoredDates(Path.Combine(renamed ? moved : watch, "photo.jpg"));
        Assert.Equal(privateTime, File.GetLastWriteTimeUtc(privatePath));
        Assert.Equal("remote", await File.ReadAllTextAsync(privatePath));
        if (renamed) Directory.Delete(watch);
    }

    [Fact]
    public async Task RemoteDeleteRemainsAnchoredWhenRootChangesDuringTombstonePersistence()
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        var watch = Path.GetDirectoryName(seed.Path)!;
        var moved = Path.Combine(directory.Path, "moved");
        var outside = Directory.CreateDirectory(Path.Combine(directory.Path, "outside")).FullName;
        var privatePath = Path.Combine(outside, "photo.jpg");
        await File.WriteAllTextAsync(privatePath, "private");
        var renamed = false;
        var store = new PathMutationStore(seed.Store)
        {
            BeforeUpsert = entry =>
            {
                if (entry.Status != SyncEntryStatus.Tombstone) return;
                try { Directory.Move(watch, moved); renamed = true; }
                catch (IOException) when (OperatingSystem.IsWindows()) { }
                if (renamed) Directory.CreateSymbolicLink(watch, outside);
            },
        };
        using var worker = CreateWorker(seed.Config, store.DatabasePath, new RecordingAssetClient(), stateStore: store);
        InitializeSecurityWorker(worker);
        await InvokeSecurityMethod(worker, "LoadPersistedStateAsync", CancellationToken.None);
        await InvokeSecurityMethod(worker, "PropagateRemoteDeletesAsync", GetOnlySecurityContext(worker), new HashSet<string>(), CancellationToken.None);
        Assert.False(File.Exists(Path.Combine(renamed ? moved : watch, "photo.jpg")));
        Assert.Equal("private", await File.ReadAllTextAsync(privatePath));
        Assert.Empty(await GetEntriesAsync(seed.Config, store.DatabasePath));
        if (renamed) Directory.Delete(watch);
    }

    [Fact]
    public async Task DisposeRetainsRootUntilBlockedCallbacksAndShutdownUploadsFinish()
    {
        using var directory = new TemporaryDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var config = CreateConfig(watch, WatchSourceSyncModes.UploadAll);
        var client = new RecordingAssetClient();
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.UploadAll);
        using var worker = CreateWorker(config, Path.Combine(directory.Path, "state.db"), client, workerLogger: logger);
        await worker.StartAsync(default);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        var context = GetOnlySecurityContext(worker);
        var root = (SecureWatchRoot)context.GetType().GetProperty("FileSystem")!.GetValue(context)!;
        var file = Path.Combine(watch, "photo.jpg");
        await File.WriteAllTextAsync(file, "authorized");
        typeof(FolderWatchWorker).GetMethod("OnFileEvent", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(worker, [context, file]);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var read = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        Func<Task> callback = async () =>
        {
            await release.Task;
            using var opened = root.OpenRead("photo.jpg");
            using var reader = new StreamReader(opened.Stream);
            read.SetResult(await reader.ReadToEndAsync());
        };
        typeof(FolderWatchWorker).GetMethod("QueueWatcherTask", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(worker, [callback]);
        worker.Dispose();
        Assert.False(worker.ExecuteTask!.IsCompleted);
        release.SetResult();
        await worker.ExecuteTask.WaitAsync(TimeSpan.FromSeconds(8));
        Assert.Equal("authorized", await read.Task.WaitAsync(TimeSpan.FromSeconds(1)));
        Assert.Equal(1, client.UploadCount);
        Assert.Single(await GetEntriesAsync(config, Path.Combine(directory.Path, "state.db")));
        Assert.Throws<ObjectDisposedException>(() => root.OpenRead("photo.jpg"));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DelayedDirectoryEventRevokesOwnershipWhenOldPathAlreadyExistsAgain(bool renamed)
    {
        using var directory = new TemporaryDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var oldPath = Directory.CreateDirectory(Path.Combine(watch, "Photos")).FullName;
        var newPath = Directory.CreateDirectory(Path.Combine(watch, "Renamed")).FullName;
        var config = CreateConfig(watch, WatchSourceSyncModes.Sync);
        config.Watch.Sources[0].AlbumName = "";
        var db = Path.Combine(directory.Path, "state.db");
        var store = new SqliteSyncStateStore(db);
        var scope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        await store.SaveOwnedAlbumAsync(scope, watch, "Photos", "owned-id", default);
        var client = new RecordingAssetClient();
        using var worker = CreateWorker(config, db, client);
        InitializeSecurityWorker(worker);
        var albumPaths = (System.Collections.Concurrent.ConcurrentDictionary<string, string>)typeof(FolderWatchWorker).GetField("_albumIdToDirName", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(worker)!;
        albumPaths["owned-id"] = "Photos";
        if (renamed) await InvokeAlbumHandler(worker, "HandleSubdirRenamedAsync", oldPath, newPath);
        else await InvokeAlbumHandler(worker, "HandleSubdirDeletedAsync", oldPath);
        Assert.Null(await store.GetOwnedAlbumAsync(scope, watch, "Photos", default));
        Assert.False(albumPaths.ContainsKey("owned-id"));
        Directory.Delete(oldPath);
        await InvokeAlbumHandler(worker, "HandleSubdirDeletedAsync", oldPath);
        Assert.Empty(client.MutatedAlbums);
    }

    private sealed class PathMutationStore(ISyncStateStore inner) : ISyncStateStore
    {
        public Action? BeforeSaveRepair { get; init; }
        public Action<SyncStateEntry>? BeforeUpsert { get; init; }
        public string DatabasePath => inner.DatabasePath;
        public Task InitializeAsync(CancellationToken ct = default) => inner.InitializeAsync(ct);
        public Task<DateTimeOffset?> GetLastSuccessfulSyncAsync(string account, CancellationToken ct = default) => inner.GetLastSuccessfulSyncAsync(account, ct);
        public Task RecordSuccessfulSyncAsync(string account, DateTimeOffset date, CancellationToken ct = default) => inner.RecordSuccessfulSyncAsync(account, date, ct);
        public Task<SyncStateEntry?> GetAsync(string account, string source, string relative, CancellationToken ct = default) => inner.GetAsync(account, source, relative, ct);
        public Task<IReadOnlyList<SyncStateEntry>> GetSourceEntriesAsync(string account, string source, CancellationToken ct = default) => inner.GetSourceEntriesAsync(account, source, ct);
        public Task UpsertAsync(SyncStateEntry entry, CancellationToken ct = default) { BeforeUpsert?.Invoke(entry); return inner.UpsertAsync(entry, ct); }
        public Task<bool> DeleteAsync(string account, string source, string relative, CancellationToken ct = default) => inner.DeleteAsync(account, source, relative, ct);
        public Task<int> DeleteExpiredTombstonesAsync(DateTimeOffset date, CancellationToken ct = default) => inner.DeleteExpiredTombstonesAsync(date, ct);
        public Task SaveTimestampRepairAsync(SyncTimestampRepair repair, CancellationToken ct = default) { BeforeSaveRepair?.Invoke(); return inner.SaveTimestampRepairAsync(repair, ct); }
        public Task<IReadOnlyList<SyncTimestampRepair>> GetTimestampRepairsAsync(string account, string source, CancellationToken ct = default) => inner.GetTimestampRepairsAsync(account, source, ct);
        public Task CompleteTimestampRepairAsync(SyncTimestampRepair repair, SyncStateEntry? updated, CancellationToken ct = default) => inner.CompleteTimestampRepairAsync(repair, updated, ct);
    }

    private static object GetOnlySecurityContext(FolderWatchWorker worker) =>
        ((IEnumerable)typeof(FolderWatchWorker).GetField("_sources", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(worker)!).Cast<object>().Single();

    private static Task InvokeSecurityMethod(FolderWatchWorker worker, string name, params object[] args) =>
        (Task)typeof(FolderWatchWorker).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(worker, args)!;
}
