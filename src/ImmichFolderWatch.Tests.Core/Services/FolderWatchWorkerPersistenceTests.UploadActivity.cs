using System.Collections.Concurrent;
using System.Security.Cryptography;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests
{
    [Fact]
    public async Task Upload_PeerRetainsReceivedBytesWhenWorkerRestartsFromLatestBackup()
    {
        using var directory = new TemporaryDirectory();
        var root = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var peer = Directory.CreateDirectory(Path.Combine(directory.Path, "peer")).FullName;
        const string name = "capture.jpg";
        var localPhoto = Path.Combine(root, name);
        var peerPhoto = Path.Combine(peer, name);
        byte[] original = [0xff, 0xd8, 0, 1, 0x7f, 0x80, 0xff, 0xd9];
        var digest = Convert.ToHexStringLower(SHA256.HashData(original));
        var lastWrite = new DateTimeOffset(2011, 8, 6, 4, 2, 0, TimeSpan.Zero);
        await File.WriteAllBytesAsync(localPhoto, original);
        File.SetLastWriteTimeUtc(localPhoto, lastWrite.UtcDateTime);

        var config = CreateConfig(root, WatchSourceSyncModes.Sync);
        var account = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        var store = new SqliteSyncStateStore(Path.Combine(directory.Path, "live.db"));
        await store.InitializeAsync();
        var beforePath = Path.Combine(directory.Path, "before.db");
        BackupActivityDatabase(store.DatabasePath, beforePath);
        var beforeHash = ActivitySha256(beforePath);
        Assert.Empty(Directory.EnumerateFileSystemEntries(peer));

        var first = await RunUploadBackupCycleAsync(config, store, account, peerPhoto);
        Assert.Contains(first.Listings, asset => asset is null);
        Assert.Equal(1, first.Uploads);
        Assert.Equal(0, first.Downloads);
        var expectedAsset = new AlbumAssetSummary("asset-" + digest, name);
        var afterPath = Path.Combine(directory.Path, "after.db");
        BackupActivityDatabase(store.DatabasePath, afterPath);
        var afterHash = ActivitySha256(afterPath);
        var after = ReadActivityState(afterPath);
        var mapping = Assert.Single(after.Mappings);
        var history = Assert.Single(after.Accounts);
        var entry = Assert.IsType<SyncStateEntry>(await store.GetAsync(account, root, name));
        var windows = OperatingSystem.IsWindows();
        Assert.Equal(new ActivityMapping(account, root, windows ? root.ToUpperInvariant() : root,
            name, windows ? name.ToUpperInvariant() : name, expectedAsset.Id, "Camera", original.Length,
            ActivityTimestamp(lastWrite), (int)SyncTransferDirection.Upload, (int)SyncEntryStatus.Synchronized,
            ActivityTimestamp(entry.LastSynchronizedAtUtc), null), mapping);
        Assert.True(entry.LastSynchronizedAtUtc <= first.LastSuccess);
        Assert.Equal((account, ActivityTimestamp(first.LastSuccess)), history);

        // The older database predates the upload. The peer already owns its separate copy.
        var stale = ReadActivityState(beforePath);
        Assert.Empty(stale.Mappings);
        Assert.Empty(stale.Accounts);
        Assert.Equal(original, await File.ReadAllBytesAsync(peerPhoto));
        Assert.Equal(original, await File.ReadAllBytesAsync(localPhoto));
        Assert.Equal(lastWrite.UtcDateTime, File.GetLastWriteTimeUtc(localPhoto));

        var restoredPath = Path.Combine(directory.Path, "restored.db");
        File.Copy(afterPath, restoredPath);
        Assert.Equal(afterHash, ActivitySha256(restoredPath));
        var second = await RunUploadBackupCycleAsync(config, new SqliteSyncStateStore(restoredPath), account, peerPhoto);
        Assert.All(second.Listings, asset => Assert.Equal(expectedAsset, asset));
        Assert.Equal(0, second.Uploads);
        Assert.Equal(0, second.Downloads);
        Assert.Equal(first.LastSuccess, second.LastSuccess);
        var restarted = ReadActivityState(restoredPath);
        Assert.Equal(mapping, Assert.Single(restarted.Mappings));
        Assert.Equal(history, Assert.Single(restarted.Accounts));
        Assert.Equal(beforeHash, ActivitySha256(beforePath));
        Assert.Equal(afterHash, ActivitySha256(afterPath));
        Assert.Equal(original, await File.ReadAllBytesAsync(localPhoto));
        Assert.Equal(lastWrite.UtcDateTime, File.GetLastWriteTimeUtc(localPhoto));
        Assert.Equal(peerPhoto, Assert.Single(Directory.EnumerateFileSystemEntries(peer)));
        var retainedDigest = ActivitySha256(peerPhoto);
        Assert.Equal(digest, retainedDigest);
        testOutput.WriteLine($"IFW_UPLOAD_PEER_SHA256={retainedDigest}");
        testOutput.WriteLine($"IFW_UPLOAD_PEER_ASSET={mapping.AssetId}");
    }

    private sealed record UploadBackupCycle(DateTimeOffset LastSuccess, int Uploads, int Downloads, AlbumAssetSummary?[] Listings);

    private static async Task<UploadBackupCycle> RunUploadBackupCycleAsync(
        AppConfig config, SqliteSyncStateStore store, string account, string peerPhoto)
    {
        var listings = new ConcurrentQueue<(string Album, AlbumAssetSummary? Asset)>();
        var client = new RecordingAssetClient
        {
            UploadHandler = (request, _, token) => ReceivePeerUploadAsync(request, peerPhoto, token),
            AlbumAssetsHandler = album =>
            {
                var asset = album == "Camera" && File.Exists(peerPhoto)
                    ? new AlbumAssetSummary("asset-" + ActivitySha256(peerPhoto), Path.GetFileName(peerPhoto))
                    : null;
                listings.Enqueue((album, asset));
                return AlbumAssetsResult.Success(asset is null ? [] : [asset]);
            },
        };
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        var status = new SyncStatusProvider();
        using var worker = CreateWorker(config, store.DatabasePath, client, workerLogger: logger,
            syncStatusProvider: status, stateStore: store);
        await worker.StartAsync(CancellationToken.None);
        try
        {
            await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
            await WaitUntilAsync(() => status.LastSyncCompletedUtc.HasValue, TimeSpan.FromSeconds(8));
        }
        finally
        {
            await worker.StopAsync(CancellationToken.None);
        }
        Assert.Null(status.LastSyncErrorMessage);
        Assert.Equal(0, logger.SyncPullFailureCount);
        Assert.NotEmpty(listings);
        Assert.All(listings, listing => Assert.Equal("Camera", listing.Album));
        var lastSuccess = Assert.IsType<DateTimeOffset>(status.LastSyncCompletedUtc);
        Assert.Equal(lastSuccess, await store.GetLastSuccessfulSyncAsync(account));
        return new(lastSuccess, client.UploadCount, client.DownloadedAssets.Count, listings.Select(listing => listing.Asset).ToArray());
    }

    private static async Task<UploadAssetResult> ReceivePeerUploadAsync(
        UploadAssetRequest request, string peerPhoto, CancellationToken token)
    {
        Assert.Equal("Camera", request.AlbumName);
        Assert.Equal(Path.GetFileName(peerPhoto), Path.GetFileName(request.FilePath));
        var file = Assert.IsType<SecureWatchFile>(request.OpenedFile);
        var length = file.Length;
        Assert.InRange(length, 1, 1024);
        var received = new byte[(int)length];
        await file.Stream.ReadExactlyAsync(received, token);
        Assert.Equal(-1, file.Stream.ReadByte());
        await using (var destination = new FileStream(peerPhoto, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            await destination.WriteAsync(received, token);
        }
        return UploadAssetResult.Success("asset-" + ActivitySha256(peerPhoto));
    }
}
