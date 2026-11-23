using System.Collections.Concurrent;
using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Runtime.InteropServices;
using System.Text.Json;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests
{
    [Fact]
    public async Task Sync_PreservesPeerTrashAndTombstoneWhenRestoringDeletionBackup()
    {
        using var directory = new TemporaryDirectory();
        var root = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var active = Directory.CreateDirectory(Path.Combine(directory.Path, "peer-album")).FullName;
        var trash = Directory.CreateDirectory(Path.Combine(directory.Path, "peer-trash")).FullName;
        var photo = Path.Combine(root, "photo.jpg");
        var peerPhoto = Path.Combine(active, "photo.jpg");
        var trashedPhoto = Path.Combine(trash, "photo.jpg");
        byte[] original = [0xff, 0xd8, 0, 0x23, 0x7f, 0x80, 0xfe, 0xff, 0xd9];
        await File.WriteAllBytesAsync(peerPhoto, original);
        var windows = OperatingSystem.IsWindows();
        if (windows) File.SetCreationTimeUtc(peerPhoto, OriginalCreated.UtcDateTime);
        File.SetLastWriteTimeUtc(peerPhoto, OriginalCreated.UtcDateTime);
        var originalPeer = ReadActivityFile(peerPhoto, original);
        var assetId = "asset-" + originalPeer.Sha256;
        var config = CreateConfig(root, WatchSourceSyncModes.Sync);
        var account = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        var store = new SqliteSyncStateStore(Path.Combine(directory.Path, "state.db"));
        var beforePath = Path.Combine(directory.Path, "before.db");
        var afterPath = Path.Combine(directory.Path, "after.db");
        using var peer = new DeletionActivityHttpPeer(assetId, peerPhoto, trashedPhoto);
        async Task AssertDurableStatusAsync(SyncEntryStatus expected)
        {
            var entry = Assert.IsType<SyncStateEntry>(await store.GetAsync(account, root, "photo.jpg"));
            Assert.Equal(assetId, entry.AssetId);
            Assert.Equal(expected, entry.Status);
        }

        ActivityFile? downloaded = null;
        var first = await RunDeletionWorkerAsync(config, store, peer, async lastSuccess =>
        {
            await AssertDurableStatusAsync(SyncEntryStatus.Synchronized);
            Assert.Equal(lastSuccess, await store.GetLastSuccessfulSyncAsync(account));
            downloaded = ReadActivityFile(photo, original);
            Assert.Equal(ActivityTimestamp(OriginalCreated), downloaded.LastWriteTimeUtc);
            Assert.Equal(windows ? ActivityTimestamp(OriginalCreated) : null, downloaded.CreationTimeUtc);
            Assert.Equal(originalPeer, ReadActivityFile(peerPhoto, original));
            Assert.Empty(Directory.GetFiles(trash));
            BackupActivityDatabase(store.DatabasePath, beforePath);
            // Remove the file from the watched directory while the shipping worker is running.
            File.Delete(photo);
            await peer.Trashed.Task.WaitAsync(TimeSpan.FromSeconds(8));
            await AssertDurableStatusAsync(SyncEntryStatus.Tombstone);
        });
        Assert.NotNull(downloaded);
        Assert.Equal(first, await store.GetLastSuccessfulSyncAsync(account));

        var firstRequests = peer.Requests.ToArray();
        Assert.Empty(peer.Errors);
        Assert.Contains(firstRequests, call => call.ListedAsset == assetId);
        Assert.Single(firstRequests, call => call.Method == "GET" && call.Path == $"/api/assets/{assetId}/original");
        Assert.Single(firstRequests, call => call.Method == "DELETE");
        BackupActivityDatabase(store.DatabasePath, afterPath);
        var beforeHash = ActivitySha256(beforePath);
        var afterHash = ActivitySha256(afterPath);
        var before = ReadActivityState(beforePath);
        var after = ReadActivityState(afterPath);
        var mapping = Assert.Single(before.Mappings);
        var history = Assert.Single(before.Accounts);
        Assert.Equal(new ActivityMapping(account, root, windows ? root.ToUpperInvariant() : root,
            "photo.jpg", windows ? "PHOTO.JPG" : "photo.jpg", assetId, "Camera", original.Length,
            downloaded.LastWriteTimeUtc, (int)SyncTransferDirection.Download, (int)SyncEntryStatus.Synchronized,
            mapping.LastSynchronizedAtUtc, null), mapping);
        Assert.Equal((account, ActivityTimestamp(first)), history);
        Assert.True(ParseDeletionTimestamp(mapping.LastSynchronizedAtUtc) <= ParseDeletionTimestamp(history.LastSuccessfulSyncUtc));
        var tombstone = Assert.Single(after.Mappings);
        Assert.NotNull(tombstone.TombstoneExpiresAtUtc);
        Assert.Equal(mapping with
        {
            Status = (int)SyncEntryStatus.Tombstone,
            LastSynchronizedAtUtc = tombstone.LastSynchronizedAtUtc,
            TombstoneExpiresAtUtc = tombstone.TombstoneExpiresAtUtc,
        }, tombstone);
        Assert.True(ParseDeletionTimestamp(tombstone.LastSynchronizedAtUtc) >= ParseDeletionTimestamp(history.LastSuccessfulSyncUtc));
        Assert.True(ParseDeletionTimestamp(tombstone.TombstoneExpiresAtUtc) > ParseDeletionTimestamp(tombstone.LastSynchronizedAtUtc));
        Assert.Equal(history, Assert.Single(after.Accounts));

        DeletionExternalState ObserveAfterDeletion()
        {
            var state = new DeletionExternalState(Directory.GetFiles(root).Select(Path.GetFileName).ToArray(),
                Directory.GetFiles(active).Select(Path.GetFileName).ToArray(), ReadActivityFile(trashedPhoto, original));
            Assert.Empty(state.LocalFiles);
            Assert.Empty(state.AlbumFiles);
            Assert.Equal(trashedPhoto, Assert.Single(Directory.GetFiles(trash)));
            Assert.Equal(originalPeer, state.TrashFile);
            return state;
        }
        var deleted = ObserveAfterDeletion();

        // Read the stale restore without starting a worker that might reconcile the old mapping.
        var stalePath = Path.Combine(directory.Path, "stale.db");
        File.Copy(beforePath, stalePath);
        var stale = ReadActivityState(stalePath);
        Assert.Equal(mapping, Assert.Single(stale.Mappings));
        Assert.Equal(history, Assert.Single(stale.Accounts));
        Assert.Equal(beforeHash, ActivitySha256(stalePath));
        var staleExternal = ObserveAfterDeletion();

        var restoredPath = Path.Combine(directory.Path, "restored.db");
        var output = Environment.GetEnvironmentVariable("IFW_QA_DELETION_ACTIVITY_OUTPUT");
        var exchange = Environment.GetEnvironmentVariable("IFW_QA_DELETION_ACTIVITY_EXCHANGE");
        var rustBackupHash = await RestoreActivityDatabaseAsync(output, exchange, "ifw-worker-deletion-backup-request-v1",
            beforePath, beforeHash, afterPath, afterHash, restoredPath);
        var received = ReadActivityState(restoredPath);
        Assert.Equal(tombstone, Assert.Single(received.Mappings));
        Assert.Equal(history, Assert.Single(received.Accounts));
        peer.Requests.Clear();
        var second = await RunDeletionWorkerAsync(config, new SqliteSyncStateStore(restoredPath), peer);
        Assert.Equal(history.LastSuccessfulSyncUtc, ActivityTimestamp(second));
        var restartRequests = peer.Requests.ToArray();
        Assert.Empty(peer.Errors);
        Assert.Contains(restartRequests, call => call.Path == "/api/search/metadata" && call.ListedAsset is null);
        Assert.All(restartRequests, call => Assert.True(call.Path == "/api/albums" || call.Path == "/api/search/metadata",
            $"Unexpected request after restore: {call.Method} {call.Path}"));
        var restart = ReadActivityState(restoredPath);
        Assert.Equal(tombstone, Assert.Single(restart.Mappings));
        Assert.Equal(history, Assert.Single(restart.Accounts));
        var restartExternal = ObserveAfterDeletion();
        Assert.NotEqual(beforeHash, afterHash);
        Assert.Equal(beforeHash, ActivitySha256(beforePath));
        Assert.Equal(afterHash, ActivitySha256(afterPath));
        testOutput.WriteLine($"IFW_DELETE_TRASH_SHA256={restartExternal.TrashFile.Sha256}");

        if (output is null) return;
        Assert.True(Path.IsPathFullyQualified(output), "The deletion activity output path must be absolute.");
        Directory.CreateDirectory(output);
        Assert.Empty(Directory.EnumerateFileSystemEntries(output));
        File.Copy(beforePath, Path.Combine(output, "before.db"));
        File.Copy(afterPath, Path.Combine(output, "after.db"));
        var exportedTrash = Path.Combine(output, "peer-trash.jpg");
        File.Copy(trashedPhoto, exportedTrash);
        Assert.Equal(restartExternal.TrashFile.Sha256, ActivitySha256(exportedTrash));
        await RecordActivityResultAsync(output, new
        {
            format = "ifw-csharp-worker-deletion-activity-v1", caseId = "restored-latest-local-deletion",
            platform = windows ? "windows" : "linux", osDescription = RuntimeInformation.OSDescription,
            osArchitecture = RuntimeInformation.OSArchitecture.ToString().ToLowerInvariant(),
            processArchitecture = RuntimeInformation.ProcessArchitecture.ToString().ToLowerInvariant(),
            testAssemblyVersion = ActivityAssemblyVersion(typeof(FolderWatchWorkerPersistenceTests)),
            testAssemblySha256 = ActivitySha256(typeof(FolderWatchWorkerPersistenceTests).Assembly.Location),
            workerAssemblyVersion = ActivityAssemblyVersion(typeof(FolderWatchWorker)),
            workerAssemblySha256 = ActivitySha256(typeof(FolderWatchWorker).Assembly.Location),
            clientAssemblyVersion = ActivityAssemblyVersion(typeof(ImmichAssetClient)),
            clientAssemblySha256 = ActivitySha256(typeof(ImmichAssetClient).Assembly.Location), accountScope = account,
            sourcePath = root, assetId,
            before = new { databaseSha256 = beforeHash, mapping, history.LastSuccessfulSyncUtc, local = downloaded, peer = originalPeer },
            after = new { databaseSha256 = afterHash, mapping = tombstone, history.LastSuccessfulSyncUtc, external = deleted, requests = firstRequests },
            staleRead = new { mapping = stale.Mappings.Single(), history.LastSuccessfulSyncUtc, external = staleExternal },
            restart = new { mapping = restart.Mappings.Single(), history.LastSuccessfulSyncUtc, external = restartExternal, requests = restartRequests },
        }, rustBackupHash);
    }

    private static DateTimeOffset ParseDeletionTimestamp(string value) =>
        DateTimeOffset.ParseExact(value, "O", CultureInfo.InvariantCulture);

    private sealed record DeletionExternalState(string?[] LocalFiles, string?[] AlbumFiles, ActivityFile TrashFile);
    private sealed record DeletionRequest(string Method, string Path, JsonElement? Body, string? ListedAsset);

    private static async Task<DateTimeOffset> RunDeletionWorkerAsync(
        AppConfig config, SqliteSyncStateStore store, DeletionActivityHttpPeer peer, Func<DateTimeOffset, Task>? afterReconciliation = null)
    {
        using var http = new HttpClient(peer, disposeHandler: false) { BaseAddress = new Uri(config.Immich.ServerApiUrl + "/") };
        var status = new SyncStatusProvider();
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        var client = new ImmichAssetClient(http, new RetrySettings { MaxAttempts = 1 }, NullLogger<ImmichAssetClient>.Instance);
        using var worker = new FolderWatchWorker(config, new AlwaysReadyChecker(), new LocalFileDeletionService(),
            new UploadBatchQueue(), client, store, status, logger);
        await worker.StartAsync(CancellationToken.None);
        try
        {
            await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
            await WaitUntilAsync(() => status.LastSyncCompletedUtc.HasValue, TimeSpan.FromSeconds(8));
            if (afterReconciliation is not null)
            {
                await afterReconciliation(Assert.IsType<DateTimeOffset>(status.LastSyncCompletedUtc));
            }
        }
        finally
        {
            await worker.StopAsync(CancellationToken.None);
        }
        Assert.Null(status.LastSyncErrorMessage);
        Assert.Equal(0, logger.SyncPullFailureCount);
        return Assert.IsType<DateTimeOffset>(status.LastSyncCompletedUtc);
    }

    private sealed class DeletionActivityHttpPeer(string assetId, string peerPhoto, string trashedPhoto) : HttpMessageHandler
    {
        public ConcurrentQueue<DeletionRequest> Requests { get; } = new();
        public ConcurrentQueue<string> Errors { get; } = new();
        public TaskCompletionSource Trashed { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            var path = request.RequestUri!.PathAndQuery;
            var method = request.Method.Method;
            try
            {
                var active = File.Exists(peerPhoto);
                JsonElement? body = request.Content is null ? null : await request.Content.ReadFromJsonAsync<JsonElement>(token);
                Requests.Enqueue(new(method, path, body, method == "POST" && path == "/api/search/metadata" && active ? assetId : null));
                if (method == "GET") Assert.Null(body);
                switch ((method, path))
                {
                    case ("GET", "/api/albums"):
                        return new(HttpStatusCode.OK) { Content = JsonContent.Create(new[] { new { id = "album-camera", albumName = "Camera" } }) };
                    case ("POST", "/api/search/metadata"):
                        Assert.True(JsonElement.DeepEquals(JsonSerializer.SerializeToElement(new { albumIds = new[] { "album-camera" }, page = 1, size = 250 }), body!.Value));
                        var items = new[] { new { id = assetId, originalFileName = "photo.jpg", fileCreatedAt = OriginalCreated, fileModifiedAt = OriginalCreated } };
                        return new(HttpStatusCode.OK) { Content = JsonContent.Create(new { assets = new { items = active ? items : [], nextPage = (int?)null } }) };
                    case ("GET", var original) when original == $"/api/assets/{assetId}/original":
                        return new(HttpStatusCode.OK) { Content = new ByteArrayContent(await File.ReadAllBytesAsync(peerPhoto, token)) };
                    case ("DELETE", "/api/assets"):
                        Assert.True(JsonElement.DeepEquals(JsonSerializer.SerializeToElement(new { ids = new[] { assetId }, force = false }), body!.Value));
                        File.Move(peerPhoto, trashedPhoto);
                        Trashed.TrySetResult();
                        return new(HttpStatusCode.NoContent);
                    default:
                        throw new InvalidOperationException($"Unexpected deletion peer request: {method} {path}");
                }
            }
            catch (Exception ex)
            {
                Errors.Enqueue($"{method} {path}: {ex.Message}");
                Trashed.TrySetException(ex);
                throw;
            }
        }
    }
}
