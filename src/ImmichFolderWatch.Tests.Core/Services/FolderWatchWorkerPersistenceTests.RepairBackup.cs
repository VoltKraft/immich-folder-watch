using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests
{
    [Fact]
    public async Task TimestampRepair_RestartsFromPendingBackupAfterFilesystemChange()
    {
        using var directory = new TemporaryDirectory();
        var seed = await SeedTimestampFileAsync(directory.Path);
        var entry = seed.Entry;
        var lastSync = entry.LastSynchronizedAtUtc.AddDays(1);
        await seed.Store.RecordSuccessfulSyncAsync(entry.AccountScope, lastSync);

        var beforeFile = ReadActivityFile(seed.Path);
        var windows = OperatingSystem.IsWindows();
        var desiredWrite = windows ? OriginalCreated.AddDays(2) : OriginalCreated;
        Assert.Equal(ActivityTimestamp(entry.LastWriteTimeUtc), beforeFile.LastWriteTimeUtc);
        Assert.NotEqual(ActivityTimestamp(desiredWrite), beforeFile.LastWriteTimeUtc);
        var beforePath = Path.Combine(directory.Path, "before.db");
        BackupActivityDatabase(seed.Store.DatabasePath, beforePath);
        var beforeHash = ActivitySha256(beforePath);

        var listedAlbums = new ConcurrentQueue<string>();
        var client = new RecordingAssetClient
        {
            AlbumAssetsHandler = album =>
            {
                listedAlbums.Enqueue(album);
                return AlbumAssetsResult.Success([DatedAsset]);
            },
        };
        var status = new SyncStatusProvider();
        using (var worker = CreateWorker(seed.Config, seed.Store.DatabasePath, client,
            syncStatusProvider: status, stateStore: new FailingTimestampCompletionStore(seed.Store)))
        {
            await worker.StartAsync(CancellationToken.None);
            try
            {
                await worker.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(8));
            }
            finally
            {
                await worker.StopAsync(CancellationToken.None);
            }
        }

        Assert.Contains("Timestamp correction", status.LastSyncErrorMessage);
        Assert.NotEmpty(listedAlbums);
        Assert.All(listedAlbums, album => Assert.Equal("Camera", album));
        Assert.Empty(client.DownloadedAssets);
        Assert.Equal(0, client.UploadCount);
        var changedFile = ReadActivityFile(seed.Path);
        Assert.Equal(beforeFile with
        {
            LastWriteTimeUtc = ActivityTimestamp(desiredWrite),
            CreationTimeUtc = windows ? ActivityTimestamp(OriginalCreated) : null,
        }, changedFile);

        var pendingPath = Path.Combine(directory.Path, "pending.db");
        BackupActivityDatabase(seed.Store.DatabasePath, pendingPath);
        var pendingHash = ActivitySha256(pendingPath);
        Assert.NotEqual(beforeHash, pendingHash);

        // Restore the older database while preserving the independently changed watch root.
        var restoredPath = Path.Combine(directory.Path, "restored.db");
        File.Copy(beforePath, restoredPath);
        Assert.Equal(beforeHash, ActivitySha256(restoredPath));
        var stale = ReadActivityState(restoredPath);
        var staleMapping = Assert.Single(stale.Mappings);
        Assert.Equal(beforeFile.LastWriteTimeUtc, staleMapping.LastWriteTimeUtc);
        Assert.Equal(ActivityTimestamp(entry.LastSynchronizedAtUtc), staleMapping.LastSynchronizedAtUtc);
        var history = Assert.Single(stale.Accounts);
        Assert.Equal((entry.AccountScope, ActivityTimestamp(lastSync)), history);
        var fileAfterStaleRestore = ReadActivityFile(seed.Path);
        Assert.Equal(changedFile, fileAfterStaleRestore);

        File.Copy(pendingPath, restoredPath, overwrite: true);
        Assert.Equal(pendingHash, ActivitySha256(restoredPath));
        var restored = new SqliteSyncStateStore(restoredPath);
        var pending = Assert.Single(await restored.GetTimestampRepairsAsync(entry.AccountScope, entry.SourcePath));
        Assert.Equal(new SyncTimestampRepair(entry, OriginalCreated, desiredWrite, beforeFile.Sha256.ToUpperInvariant()), pending);
        Assert.Equal(entry, Assert.Single(await restored.GetSourceEntriesAsync(entry.AccountScope, entry.SourcePath)));
        Assert.Equal(lastSync, await restored.GetLastSuccessfulSyncAsync(entry.AccountScope));

        var completedPath = Path.Combine(directory.Path, "completed.db");
        var restart = await RunActivityWorkerAsync(seed.Config, restored, entry.AccountScope, completedPath);
        Assert.Equal(entry with { LastWriteTimeUtc = desiredWrite }, restart.Entry);
        Assert.Equal(lastSync, restart.LastSuccess);
        Assert.Equal(0, restart.Downloads);
        Assert.Equal(0, restart.Uploads);
        var completed = ReadActivityState(completedPath);
        var completedMapping = Assert.Single(completed.Mappings);
        Assert.Equal(staleMapping with { LastWriteTimeUtc = changedFile.LastWriteTimeUtc }, completedMapping);
        Assert.Equal(history, Assert.Single(completed.Accounts));
        Assert.Empty(await restored.GetTimestampRepairsAsync(entry.AccountScope, entry.SourcePath));
        var restartedFile = ReadActivityFile(seed.Path);
        Assert.Equal(changedFile, restartedFile);

        // Completion belongs to the restored copy. The original database still contains the pending intent.
        Assert.Equal(pending, Assert.Single(await seed.Store.GetTimestampRepairsAsync(entry.AccountScope, entry.SourcePath)));
        Assert.Equal(beforeHash, ActivitySha256(beforePath));
        Assert.Equal(pendingHash, ActivitySha256(pendingPath));

        var output = Environment.GetEnvironmentVariable("IFW_QA_REPAIR_ACTIVITY_OUTPUT");
        if (output is null) return;
        Assert.True(Path.IsPathFullyQualified(output), "The repair activity output path must be absolute.");
        Directory.CreateDirectory(output);
        Assert.Empty(Directory.EnumerateFileSystemEntries(output));
        foreach (var snapshot in new[] { beforePath, pendingPath, completedPath })
            File.Copy(snapshot, Path.Combine(output, Path.GetFileName(snapshot)));
        var photo = Path.Combine(output, "photo.jpg");
        File.Copy(seed.Path, photo);
        if (windows) File.SetCreationTimeUtc(photo, File.GetCreationTimeUtc(seed.Path));
        Assert.Equal(restartedFile, ReadActivityFile(photo));
        await RecordActivityResultAsync(output, new
        {
            format = "ifw-csharp-worker-repair-activity-v1",
            platform = windows ? "windows" : "linux",
            osDescription = RuntimeInformation.OSDescription,
            osArchitecture = RuntimeInformation.OSArchitecture.ToString().ToLowerInvariant(),
            processArchitecture = RuntimeInformation.ProcessArchitecture.ToString().ToLowerInvariant(),
            workerAssemblyVersion = ActivityAssemblyVersion(typeof(FolderWatchWorker)),
            workerAssemblySha256 = ActivitySha256(typeof(FolderWatchWorker).Assembly.Location),
            testAssemblyVersion = ActivityAssemblyVersion(typeof(FolderWatchWorkerPersistenceTests)),
            testAssemblySha256 = ActivitySha256(typeof(FolderWatchWorkerPersistenceTests).Assembly.Location),
            before = new { databaseSha256 = beforeHash, mapping = staleMapping, history.LastSuccessfulSyncUtc, file = beforeFile },
            interrupted = new { databaseSha256 = pendingHash, pending, file = changedFile, albumLists = listedAlbums.Count,
                downloads = client.DownloadedAssets.Count, uploads = client.UploadCount, status.LastSyncErrorMessage },
            staleRestore = new { file = fileAfterStaleRestore },
            restart = new { databaseSha256 = ActivitySha256(completedPath), mapping = completedMapping,
                history.LastSuccessfulSyncUtc, file = restartedFile, restart.AlbumLists, restart.Downloads, restart.Uploads },
        }, rustBackupHash: null);
    }
}
