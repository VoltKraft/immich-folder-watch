using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
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
        var peerExisted = File.Exists(peerPhoto);
        var localBefore = ReadActivityFile(localPhoto, original);

        var first = await RunUploadBackupCycleAsync(config, store, account, peerPhoto);
        Assert.Contains(first.Listings, asset => asset is null);
        Assert.Equal(1, first.Uploads);
        Assert.Equal(0, first.Downloads);
        var expectedAsset = new AlbumAssetSummary("asset-" + digest, name);
        Assert.All(first.Listings, asset => Assert.True(asset is null || asset == expectedAsset));
        var localAfter = ReadActivityFile(localPhoto, original);
        var peerAfter = ReadActivityFile(peerPhoto, original);
        Assert.Equal(localBefore, localAfter);
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
        var stalePeer = ReadActivityFile(peerPhoto, original);
        var staleLocal = ReadActivityFile(localPhoto, original);
        Assert.Equal(peerAfter, stalePeer);
        Assert.Equal(localAfter, staleLocal);

        var output = Environment.GetEnvironmentVariable("IFW_QA_UPLOAD_ACTIVITY_OUTPUT");
        var exchange = Environment.GetEnvironmentVariable("IFW_QA_UPLOAD_ACTIVITY_EXCHANGE");
        var restoredPath = Path.Combine(directory.Path, "restored.db");
        var rustBackupHash = await RestoreActivityDatabaseAsync(output, exchange, "ifw-worker-upload-backup-request-v1",
            beforePath, beforeHash, afterPath, afterHash, restoredPath);
        var received = ReadActivityState(restoredPath);
        Assert.Equal(mapping, Assert.Single(received.Mappings));
        Assert.Equal(history, Assert.Single(received.Accounts));
        var second = await RunUploadBackupCycleAsync(config, new SqliteSyncStateStore(restoredPath), account, peerPhoto);
        Assert.All(second.Listings, asset => Assert.Equal(expectedAsset, asset));
        Assert.Equal(0, second.Uploads);
        Assert.Equal(0, second.Downloads);
        Assert.Equal(first.LastSuccess, second.LastSuccess);
        var restarted = ReadActivityState(restoredPath);
        var restartedMapping = Assert.Single(restarted.Mappings);
        var restartedHistory = Assert.Single(restarted.Accounts);
        Assert.Equal(mapping, restartedMapping);
        Assert.Equal(history, restartedHistory);
        Assert.Equal(beforeHash, ActivitySha256(beforePath));
        Assert.Equal(afterHash, ActivitySha256(afterPath));
        var restartedLocal = ReadActivityFile(localPhoto, original);
        var restartedPeer = ReadActivityFile(peerPhoto, original);
        Assert.Equal(localBefore, restartedLocal);
        Assert.Equal(ActivityTimestamp(lastWrite), restartedLocal.LastWriteTimeUtc);
        Assert.Equal(peerAfter, restartedPeer);
        Assert.Equal(peerPhoto, Assert.Single(Directory.EnumerateFileSystemEntries(peer)));
        var retainedDigest = ActivitySha256(peerPhoto);
        Assert.Equal(digest, retainedDigest);
        testOutput.WriteLine($"IFW_UPLOAD_PEER_SHA256={retainedDigest}");
        testOutput.WriteLine($"IFW_UPLOAD_PEER_ASSET={mapping.AssetId}");

        if (output is null) return;
        Assert.True(Path.IsPathFullyQualified(output), "The upload activity output path must be absolute.");
        Assert.True(windows || OperatingSystem.IsLinux(), "The upload reference requires Windows or Linux.");
        Directory.CreateDirectory(output);
        Assert.Empty(Directory.EnumerateFileSystemEntries(output));
        File.Copy(beforePath, Path.Combine(output, "before.db"));
        File.Copy(afterPath, Path.Combine(output, "after.db"));
        File.Copy(localPhoto, Path.Combine(output, "capture.jpg"));
        File.Copy(peerPhoto, Path.Combine(output, "peer.jpg"));
        await RecordActivityResultAsync(output, new
        {
            format = "ifw-csharp-worker-upload-activity-v1", caseId = "restored-latest-upload",
            platform = windows ? "windows" : "linux", osDescription = RuntimeInformation.OSDescription,
            osArchitecture = RuntimeInformation.OSArchitecture.ToString().ToLowerInvariant(),
            processArchitecture = RuntimeInformation.ProcessArchitecture.ToString().ToLowerInvariant(),
            testAssemblyVersion = ActivityAssemblyVersion(typeof(FolderWatchWorkerPersistenceTests)),
            workerAssemblyVersion = ActivityAssemblyVersion(typeof(FolderWatchWorker)), accountScope = account, sourcePath = root,
            before = new { databaseSha256 = beforeHash, local = localBefore, peerExisted },
            after = new { databaseSha256 = afterHash, mapping, history.LastSuccessfulSyncUtc, local = localAfter, peer = peerAfter,
                first.Uploads, first.Downloads, first.Listings, first.RejectedRequests },
            staleRead = new { mappingCount = stale.Mappings.Count, accountStatusCount = stale.Accounts.Count,
                local = staleLocal, peer = stalePeer },
            restart = new { mapping = restartedMapping, restartedHistory.LastSuccessfulSyncUtc, local = restartedLocal, peer = restartedPeer,
                second.Uploads, second.Downloads, second.Listings, second.RejectedRequests },
        }, rustBackupHash);
    }

    private sealed record PeerRequest(string Method, string[] Arguments);

    [Fact]
    public async Task Upload_PeerRejectsAndRecordsEveryUnexpectedWriteAndDownload()
    {
        using var directory = new TemporaryDirectory();
        using var root = SecureWatchRoot.Open(directory.Path);
        using var lease = root.CreateDownload("probe.jpg");
        var peer = new UploadActivityPeer(Path.Combine(directory.Path, "capture.jpg"));
        IImmichAssetClient client = peer;
        var token = CancellationToken.None;

        async Task CheckAsync(Func<Task> call, string method, params string[] arguments)
        {
            var error = await Assert.ThrowsAsync<InvalidOperationException>(call);
            Assert.Contains(method, error.Message, StringComparison.Ordinal);
            Assert.True(peer.RejectedRequests.TryDequeue(out var request));
            Assert.Equal(method, request.Method);
            Assert.Equal(arguments, request.Arguments);
        }

        await CheckAsync(() => client.AddAssetsToAlbumAsync("Camera", ["asset-a", "asset-b"], token),
            nameof(client.AddAssetsToAlbumAsync), "Camera", "asset-a", "asset-b");
        await CheckAsync(() => client.RemoveAssetsFromAlbumAsync("Camera", ["asset-b"], token),
            nameof(client.RemoveAssetsFromAlbumAsync), "Camera", "asset-b");
        await CheckAsync(() => client.TrashAssetsAsync(["asset-a"], token), nameof(client.TrashAssetsAsync), "asset-a");
        await CheckAsync(() => client.TrashAssetsAsync([], token), nameof(client.TrashAssetsAsync));
        await CheckAsync(() => client.EnsureAlbumAsync("Camera", token), nameof(client.EnsureAlbumAsync), "Camera");
        await CheckAsync(() => client.CreateOwnedAlbumAsync("Camera", token), nameof(client.CreateOwnedAlbumAsync), "Camera");
        await CheckAsync(() => client.DeleteAlbumAsync("Camera", token), nameof(client.DeleteAlbumAsync), "Camera");
        await CheckAsync(() => client.DeleteAlbumByIdAsync("album-a", token), nameof(client.DeleteAlbumByIdAsync), "album-a");
        await CheckAsync(() => client.RenameAlbumAsync("Camera", "Other", token), nameof(client.RenameAlbumAsync), "Camera", "Other");
        await CheckAsync(() => client.RenameAlbumByIdAsync("album-a", "Other", token), nameof(client.RenameAlbumByIdAsync), "album-a", "Other");
        await CheckAsync(() => client.DownloadAssetAsync("asset-a", Path.Combine(directory.Path, "unused.jpg"), token),
            nameof(client.DownloadAssetAsync), "asset-a");
        await CheckAsync(() => client.DownloadAssetAsync("asset-a", lease, token), nameof(client.DownloadAssetAsync), "asset-a");
        Assert.Empty(peer.RejectedRequests);
    }

    private sealed record UploadBackupCycle(DateTimeOffset LastSuccess, int Uploads, int Downloads,
        AlbumAssetSummary?[] Listings, PeerRequest[] RejectedRequests);

    private static async Task<UploadBackupCycle> RunUploadBackupCycleAsync(
        AppConfig config, SqliteSyncStateStore store, string account, string peerPhoto)
    {
        var client = new UploadActivityPeer(peerPhoto);
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        var status = new SyncStatusProvider();
        using var worker = new FolderWatchWorker(config, new AlwaysReadyChecker(), new LocalFileDeletionService(),
            new UploadBatchQueue(), client, store, status, logger);
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
        Assert.Empty(client.RejectedRequests);
        Assert.Null(status.LastSyncErrorMessage);
        Assert.Equal(0, logger.SyncPullFailureCount);
        Assert.NotEmpty(client.Listings);
        Assert.All(client.Listings, listing => Assert.Equal("Camera", listing.Album));
        var lastSuccess = Assert.IsType<DateTimeOffset>(status.LastSyncCompletedUtc);
        Assert.Equal(lastSuccess, await store.GetLastSuccessfulSyncAsync(account));
        return new(lastSuccess, client.UploadCount, client.RejectedRequests.Count(call => call.Method == nameof(IImmichAssetClient.DownloadAssetAsync)),
            client.Listings.Select(listing => listing.Asset).ToArray(), client.RejectedRequests.ToArray());
    }

    private sealed class UploadActivityPeer(string peerPhoto) : IImmichAssetClient
    {
        private int _uploads;
        public int UploadCount => Volatile.Read(ref _uploads);
        public ConcurrentQueue<(string Album, AlbumAssetSummary? Asset)> Listings { get; } = new();
        public ConcurrentQueue<PeerRequest> RejectedRequests { get; } = new();

        public Task<UploadAssetResult> UploadAssetAsync(UploadAssetRequest request, CancellationToken token)
        {
            Interlocked.Increment(ref _uploads);
            return ReceivePeerUploadAsync(request, peerPhoto, token);
        }

        public Task<UploadAssetResult> UploadAssetAttemptAsync(UploadAssetRequest request, CancellationToken token) =>
            UploadAssetAsync(request, token);

        public Task<AlbumAssetsResult> GetAlbumAssetsAsync(string albumName, CancellationToken token)
        {
            var asset = albumName == "Camera" && File.Exists(peerPhoto)
                ? new AlbumAssetSummary("asset-" + ActivitySha256(peerPhoto), Path.GetFileName(peerPhoto))
                : null;
            Listings.Enqueue((albumName, asset));
            return Task.FromResult(AlbumAssetsResult.Success(asset is null ? [] : [asset]));
        }

        public Task PingAsync(CancellationToken token) => Task.CompletedTask;
        public Task<AlbumListResult> ListAlbumsAsync(CancellationToken token) => Task.FromResult(AlbumListResult.Success([]));
        public Task<UnassignedAssetsResult> GetUnassignedAssetsAsync(CancellationToken token) => Task.FromResult(UnassignedAssetsResult.Success([]));

        // Record the attempt even when the calling worker catches the failure or supplies an empty ID list.
        private Task<T> Reject<T>(string method, params string[] arguments)
        {
            RejectedRequests.Enqueue(new(method, arguments));
            return Task.FromException<T>(new InvalidOperationException($"Unexpected upload peer request: {method}"));
        }

        public Task<DownloadAssetResult> DownloadAssetAsync(string assetId, string destinationPath, CancellationToken token) =>
            Reject<DownloadAssetResult>(nameof(DownloadAssetAsync), assetId);
        public Task<DownloadAssetResult> DownloadAssetAsync(string assetId, SecureDownloadLease destination, CancellationToken token) =>
            Reject<DownloadAssetResult>(nameof(DownloadAssetAsync), assetId);
        public Task<AlbumMembershipUpdateResult> AddAssetsToAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken token) =>
            Reject<AlbumMembershipUpdateResult>(nameof(AddAssetsToAlbumAsync), [albumName, .. assetIds]);
        public Task<AlbumMembershipUpdateResult> RemoveAssetsFromAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken token) =>
            Reject<AlbumMembershipUpdateResult>(nameof(RemoveAssetsFromAlbumAsync), [albumName, .. assetIds]);
        public Task<TrashAssetsResult> TrashAssetsAsync(IReadOnlyList<string> assetIds, CancellationToken token) =>
            Reject<TrashAssetsResult>(nameof(TrashAssetsAsync), [.. assetIds]);
        public Task<EnsureAlbumResult> EnsureAlbumAsync(string albumName, CancellationToken token) =>
            Reject<EnsureAlbumResult>(nameof(EnsureAlbumAsync), albumName);
        public Task<EnsureAlbumResult> CreateOwnedAlbumAsync(string albumName, CancellationToken token) =>
            Reject<EnsureAlbumResult>(nameof(CreateOwnedAlbumAsync), albumName);
        public Task<DeleteAlbumResult> DeleteAlbumAsync(string albumName, CancellationToken token) =>
            Reject<DeleteAlbumResult>(nameof(DeleteAlbumAsync), albumName);
        public Task<RenameAlbumResult> RenameAlbumAsync(string oldAlbumName, string newAlbumName, CancellationToken token) =>
            Reject<RenameAlbumResult>(nameof(RenameAlbumAsync), oldAlbumName, newAlbumName);
        public Task<DeleteAlbumResult> DeleteAlbumByIdAsync(string albumId, CancellationToken token) =>
            Reject<DeleteAlbumResult>(nameof(DeleteAlbumByIdAsync), albumId);
        public Task<RenameAlbumResult> RenameAlbumByIdAsync(string albumId, string newName, CancellationToken token) =>
            Reject<RenameAlbumResult>(nameof(RenameAlbumByIdAsync), albumId, newName);
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
