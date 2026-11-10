using System.Reflection;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SubfolderDelete_RequiresPersistedOwnership(bool owned)
    {
        using var directory = new TemporaryDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var db = Path.Combine(directory.Path, "state.db");
        var config = CreateConfig(watch, WatchSourceSyncModes.Sync);
        config.Watch.Sources[0].AlbumName = "";
        var store = new SqliteSyncStateStore(db);
        if (owned)
        {
            await store.SaveOwnedAlbumAsync(SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey), watch, "Photos", "owned-id", default);
        }
        var client = new RecordingAssetClient();
        using var worker = CreateWorker(config, db, client);
        InitializeSecurityWorker(worker);
        await InvokeAlbumHandler(worker, "HandleSubdirDeletedAsync", Path.Combine(watch, "Photos"));
        Assert.Equal(owned ? new[] { "delete:owned-id" } : Array.Empty<string>(), client.MutatedAlbums.ToArray());
        Assert.Empty(client.TrashedAssets);
    }

    [Fact]
    public async Task FailedRenameRevokesOldPathBeforeItCanBeRecreatedAndDeleted()
    {
        using var directory = new TemporaryDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var renamed = Directory.CreateDirectory(Path.Combine(watch, "Renamed")).FullName;
        var db = Path.Combine(directory.Path, "state.db");
        var config = CreateConfig(watch, WatchSourceSyncModes.Sync);
        config.Watch.Sources[0].AlbumName = "";
        var store = new SqliteSyncStateStore(db);
        var scope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        await store.SaveOwnedAlbumAsync(scope, watch, "Photos", "owned-id", default);
        var client = new RecordingAssetClient { FailAlbumRename = true };
        using var worker = CreateWorker(config, db, client);
        InitializeSecurityWorker(worker);
        await InvokeAlbumHandler(worker, "HandleSubdirRenamedAsync", Path.Combine(watch, "Photos"), renamed);
        Assert.Null(await store.GetOwnedAlbumAsync(scope, watch, "Photos", default));
        await InvokeAlbumHandler(worker, "HandleSubdirDeletedAsync", Path.Combine(watch, "Photos"));
        Assert.Equal(new[] { "rename:owned-id" }, client.MutatedAlbums.ToArray());
    }

    [Fact]
    public async Task WorkerRestartRevokesAuthorityForOfflineReplacedDirectory()
    {
        using var directory = new TemporaryDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var db = Path.Combine(directory.Path, "state.db");
        var config = CreateConfig(watch, WatchSourceSyncModes.Sync);
        config.Watch.Sources[0].AlbumName = "";
        var store = new SqliteSyncStateStore(db);
        var scope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        await store.SaveOwnedAlbumAsync(scope, watch, "Photos", "owned-before-restart", default);
        var client = new RecordingAssetClient();
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var worker = CreateWorker(config, db, client, workerLogger: logger);
        await worker.StartAsync(default);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(default);
        Assert.Null(await store.GetOwnedAlbumAsync(scope, watch, "Photos", default));
        await InvokeAlbumHandler(worker, "HandleSubdirDeletedAsync", Path.Combine(watch, "Photos"));
        Assert.Empty(client.MutatedAlbums);
    }

    [Fact]
    public async Task RapidRenameRevokesOldAuthorityEvenWhenIntermediateDestinationIsGone()
    {
        using var directory = new TemporaryDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var db = Path.Combine(directory.Path, "state.db");
        var config = CreateConfig(watch, WatchSourceSyncModes.Sync);
        config.Watch.Sources[0].AlbumName = "";
        var store = new SqliteSyncStateStore(db);
        var scope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        await store.SaveOwnedAlbumAsync(scope, watch, "Photos", "owned-id", default);
        var client = new RecordingAssetClient();
        using var worker = CreateWorker(config, db, client);
        InitializeSecurityWorker(worker);
        await InvokeAlbumHandler(worker, "HandleSubdirRenamedAsync", Path.Combine(watch, "Photos"), Path.Combine(watch, "AlreadyGone"));
        Assert.Null(await store.GetOwnedAlbumAsync(scope, watch, "Photos", default));
        await InvokeAlbumHandler(worker, "HandleSubdirDeletedAsync", Path.Combine(watch, "Photos"));
        Assert.Empty(client.MutatedAlbums);
    }

    private static void InitializeSecurityWorker(FolderWatchWorker worker)
    {
        typeof(FolderWatchWorker).GetMethod("RegisterWatchers", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(worker, null);
        // Drive callbacks deterministically without asynchronous filesystem events.
        typeof(FolderWatchWorker).GetMethod("DisposeWatchers", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(worker, null);
    }

    private static Task InvokeAlbumHandler(FolderWatchWorker worker, string name, params string[] paths) =>
        (Task)typeof(FolderWatchWorker).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(worker, paths.Cast<object>().ToArray())!;
}
