using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests
{
    [Theory]
    [InlineData(TransferOrders.NewestFirst)]
    [InlineData(TransferOrders.OldestFirst)]
    public async Task Sync_DownloadOrderSpansAlbumsAndSourcesUsingOriginalCreation(string order)
    {
        using var directory = new TemporaryDirectory();
        var root = Directory.CreateDirectory(Path.Combine(directory.Path, "library")).FullName;
        var other = Directory.CreateDirectory(Path.Combine(directory.Path, "other")).FullName;
        var config = CreateConfig(root, WatchSourceSyncModes.Sync);
        config.Watch.Sources[0].AlbumName = "";
        config.Watch.TransferOrder = order;
        config.Watch.Sources.Add(new WatchSourceSettings { Path = other, AlbumName = "Single", SyncMode = WatchSourceSyncModes.Sync, Extensions = [".jpg"] });
        var prematureDownload = false;
        RecordingAssetClient? client = null;
        client = new RecordingAssetClient
        {
            UnassignedAssets = [OrderAsset("unassigned", 2025, 2029), new("unknown", "unknown.jpg")],
            RemoteAlbums = [new("a", "Older"), new("b", "Latest")],
            AlbumAssetsHandler = album =>
            {
                prematureDownload |= !client!.DownloadedAssets.IsEmpty;
                return AlbumAssetsResult.Success(album switch
                {
                    "Older" => [OrderAsset("old-album", 2024, 2028)],
                    "Latest" => [OrderAsset("today", 2026, 2023)],
                    _ => [OrderAsset("other-source", 2025, 2027) with { FileCreatedAt = new DateTimeOffset(2025, 6, 1, 0, 0, 0, TimeSpan.Zero) }],
                });
            },
        };
        using var worker = CreateWorker(config, Path.Combine(directory.Path, "state.db"), client);
        await worker.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => client.DownloadedAssets.Count == 5, TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);
        Assert.False(prematureDownload);
        var dated = new[] { "old-album", "unassigned", "other-source", "today" };
        Assert.Equal((order == TransferOrders.NewestFirst ? dated.Reverse() : dated).Append("unknown"), client.DownloadedAssets.ToArray());
        Assert.Equal("today", await File.ReadAllTextAsync(Path.Combine(root, "Latest", "today.jpg")));
        Assert.Equal(0, client.UploadCount);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Sync_GlobalDownloadOrderProtectsLocalFilesAndListingFailures(bool listingFailure)
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        seed.Config.Watch.Sources[0].AlbumName = "";
        await seed.Store.UpsertAsync(seed.Entry with { AlbumName = "" });
        var root = Path.GetDirectoryName(seed.Path)!;
        var local = Path.Combine(root, "unassigned.jpg");
        var client = new RecordingAssetClient
        {
            UnassignedAssets = [OrderAsset("unassigned", 2025, 2025)],
            RemoteAlbums = [new("a", "First"), new("b", "Latest")],
            AlbumAssetsHandler = album =>
            {
                if (album == "Latest") return AlbumAssetsResult.Success([OrderAsset("today", 2026, 2026)]);
                if (listingFailure) return AlbumAssetsResult.Failure(null, "Synthetic listing error");
                File.WriteAllText(local, "local-edit");
                return AlbumAssetsResult.Success([new AlbumAssetSummary("remote", "photo.jpg")]);
            },
        };
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var worker = CreateWorker(seed.Config, seed.Store.DatabasePath, client, workerLogger: logger);
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);
        if (listingFailure)
        {
            Assert.True(File.Exists(seed.Path));
            Assert.Equal(new[] { "today", "unassigned" }, client.DownloadedAssets.ToArray());
        }
        else
        {
            Assert.Equal("local-edit", await File.ReadAllTextAsync(local));
            Assert.DoesNotContain("unassigned", client.DownloadedAssets);
            Assert.Equal("today", client.DownloadedAssets.First());
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Sync_GlobalDownloadOrderPreservesDownloadsInOverlappingRoots(bool identicalRoot)
    {
        using var directory = new TemporaryDirectory();
        var parent = Directory.CreateDirectory(Path.Combine(directory.Path, "library")).FullName;
        var child = identicalRoot ? parent : Directory.CreateDirectory(Path.Combine(parent, "nested")).FullName;
        var config = CreateConfig(parent, WatchSourceSyncModes.Sync);
        config.Watch.Sources[0].AlbumName = "Empty";
        config.Watch.Sources.Add(new WatchSourceSettings { Path = child, AlbumName = "Latest", SyncMode = WatchSourceSyncModes.Sync, Extensions = [".jpg"] });
        var client = new RecordingAssetClient
        {
            AlbumAssetsHandler = album => AlbumAssetsResult.Success(album == "Latest" ? [OrderAsset("today", 2026, 2026)] : []),
        };
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync, sourceCount: 2);
        using var worker = CreateWorker(config, Path.Combine(directory.Path, "state.db"), client, workerLogger: logger);
        await worker.StartAsync(CancellationToken.None);
        await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
        await worker.StopAsync(CancellationToken.None);
        Assert.Equal(new[] { "today" }, client.DownloadedAssets.ToArray());
        Assert.Equal("today", await File.ReadAllTextAsync(Path.Combine(child, "today.jpg")));
    }

    private static AlbumAssetSummary OrderAsset(string id, int createdYear, int modifiedYear) => new(id, id + ".jpg",
        new DateTimeOffset(modifiedYear, 1, 1, 0, 0, 0, TimeSpan.Zero), new DateTimeOffset(createdYear, 1, 1, 0, 0, 0, TimeSpan.Zero));
}
