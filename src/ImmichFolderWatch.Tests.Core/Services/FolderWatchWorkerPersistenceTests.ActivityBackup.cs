using System.Collections.Concurrent;
using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using Microsoft.Data.Sqlite;
using Xunit.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed partial class FolderWatchWorkerPersistenceTests(ITestOutputHelper testOutput)
{
    [Fact]
    public async Task Download_RetainsBeforeAndAfterBackupsAndRestartsFromLatest()
    {
        using var directory = new TemporaryDirectory();
        var root = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var photo = Path.Combine(root, "photo.jpg");
        var config = CreateConfig(root, WatchSourceSyncModes.Sync);
        var account = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        var store = new SqliteSyncStateStore(Path.Combine(directory.Path, "state.db"));
        await store.InitializeAsync();

        var beforePath = Path.Combine(directory.Path, "before.db");
        BackupActivityDatabase(store.DatabasePath, beforePath);
        var beforeHash = ActivitySha256(beforePath);
        var before = ReadActivityState(beforePath);
        var fileExisted = File.Exists(photo);
        Assert.Empty(before.Mappings);
        Assert.Empty(before.Accounts);
        Assert.False(fileExisted);

        var afterPath = Path.Combine(directory.Path, "after.db");
        var first = await RunActivityWorkerAsync(config, store, account, afterPath);
        var afterHash = ActivitySha256(afterPath);
        var after = ReadActivityState(afterPath);
        var installed = ReadActivityFile(photo);
        var mapping = Assert.Single(after.Mappings);
        var lastSuccess = Assert.Single(after.Accounts);
        var windows = OperatingSystem.IsWindows();
        Assert.Equal(ActivityTimestamp(windows ? OriginalCreated.AddDays(2) : OriginalCreated), installed.LastWriteTimeUtc);
        Assert.Equal(windows ? ActivityTimestamp(OriginalCreated) : null, installed.CreationTimeUtc);
        Assert.Equal(new ActivityMapping(account, root, windows ? root.ToUpperInvariant() : root,
            "photo.jpg", windows ? "PHOTO.JPG" : "photo.jpg", "remote", "Camera", 6, installed.LastWriteTimeUtc,
            (int)SyncTransferDirection.Download, (int)SyncEntryStatus.Synchronized,
            ActivityTimestamp(first.Entry.LastSynchronizedAtUtc), null), mapping);
        Assert.Equal((account, ActivityTimestamp(first.LastSuccess)), lastSuccess);
        Assert.True(first.Entry.LastSynchronizedAtUtc <= first.LastSuccess);
        Assert.Equal(1, first.Downloads);
        Assert.Equal(0, first.Uploads);

        // Opening the older snapshot reveals the missing transfer while the downloaded file still exists.
        var stale = ReadActivityState(beforePath);
        Assert.Empty(stale.Mappings);
        Assert.Empty(stale.Accounts);
        var fileAfterStaleRead = ReadActivityFile(photo);
        Assert.Equal(installed, fileAfterStaleRead);

        var output = Environment.GetEnvironmentVariable("IFW_QA_ACTIVITY_OUTPUT");
        var exchange = Environment.GetEnvironmentVariable("IFW_QA_ACTIVITY_EXCHANGE");
        var restoredPath = Path.Combine(directory.Path, "restored.db");
        string? rustBackupHash = null;
        if (exchange is null)
        {
            File.Copy(afterPath, restoredPath);
            Assert.Equal(afterHash, ActivitySha256(restoredPath));
        }
        else
        {
            Assert.NotNull(output);
            Assert.True(Path.IsPathFullyQualified(output), "The exchange requires an absolute activity output path.");
            Assert.True(Path.IsPathFullyQualified(exchange), "The exchange directory must be absolute.");
            Assert.NotEqual(".", Path.GetRelativePath(output, exchange));
            rustBackupHash = await ReceiveActivityBackupAsync(exchange, beforePath, beforeHash, afterPath, afterHash, restoredPath);
            var received = ReadActivityState(restoredPath);
            Assert.Equal(mapping, Assert.Single(received.Mappings));
            Assert.Equal(lastSuccess, Assert.Single(received.Accounts));
            Assert.Equal(installed, ReadActivityFile(photo));
        }
        var restoredStore = new SqliteSyncStateStore(restoredPath);
        var second = await RunActivityWorkerAsync(config, restoredStore, account);
        Assert.Equal(first.Entry, second.Entry);
        Assert.Equal(first.LastSuccess, second.LastSuccess);
        var restarted = ReadActivityState(restoredPath);
        var restartedMapping = Assert.Single(restarted.Mappings);
        var restartedSuccess = Assert.Single(restarted.Accounts);
        var restartedFile = ReadActivityFile(photo);
        Assert.Equal(mapping, restartedMapping);
        Assert.Equal(lastSuccess, restartedSuccess);
        Assert.Equal(installed, restartedFile);
        Assert.Equal(0, second.Downloads);
        Assert.Equal(0, second.Uploads);

        var otherAccount = SyncAccountScope.Create(config.Immich.ServerApiUrl, "other-test-key");
        Assert.Null(await restoredStore.GetLastSuccessfulSyncAsync(otherAccount));
        Assert.Null(await restoredStore.GetAsync(otherAccount, root, "photo.jpg"));
        Assert.Null(await restoredStore.GetAsync(account, Path.Combine(directory.Path, "other-watch"), "photo.jpg"));
        Assert.Equal(beforeHash, ActivitySha256(beforePath));
        Assert.Equal(afterHash, ActivitySha256(afterPath));
        Assert.NotEqual(beforeHash, afterHash);

        if (output is null) return;
        Assert.True(Path.IsPathFullyQualified(output), "The activity output path must be absolute.");
        Assert.True(windows || OperatingSystem.IsLinux(), "The activity reference requires Windows or Linux.");
        Directory.CreateDirectory(output);
        Assert.Empty(Directory.EnumerateFileSystemEntries(output));
        File.Copy(beforePath, Path.Combine(output, "before.db"));
        File.Copy(afterPath, Path.Combine(output, "after.db"));
        var exportedPhoto = Path.Combine(output, "photo.jpg");
        File.Copy(photo, exportedPhoto);
        if (windows) File.SetCreationTimeUtc(exportedPhoto, File.GetCreationTimeUtc(photo));
        Assert.Equal(installed, ReadActivityFile(exportedPhoto));
        var evidence = new
        {
            format = "ifw-csharp-worker-download-activity-v1",
            caseId = "restored-latest-download",
            platform = windows ? "windows" : "linux",
            osDescription = RuntimeInformation.OSDescription,
            osArchitecture = RuntimeInformation.OSArchitecture.ToString().ToLowerInvariant(),
            processArchitecture = RuntimeInformation.ProcessArchitecture.ToString().ToLowerInvariant(),
            testAssemblyVersion = ActivityAssemblyVersion(typeof(FolderWatchWorkerPersistenceTests)),
            workerAssemblyVersion = ActivityAssemblyVersion(typeof(FolderWatchWorker)),
            accountScope = account,
            sourcePath = root,
            before = new
            {
                databaseSha256 = beforeHash, mappingCount = before.Mappings.Count,
                accountStatusCount = before.Accounts.Count, fileExisted,
            },
            after = new
            {
                databaseSha256 = afterHash, mapping, lastSuccessfulSyncUtc = lastSuccess.LastSuccessfulSyncUtc,
                file = installed, first.AlbumLists, first.Downloads, first.Uploads,
            },
            staleRead = new
            {
                mappingCount = stale.Mappings.Count, accountStatusCount = stale.Accounts.Count, file = fileAfterStaleRead,
            },
            restart = new
            {
                mapping = restartedMapping, lastSuccessfulSyncUtc = restartedSuccess.LastSuccessfulSyncUtc, file = restartedFile,
                second.AlbumLists, second.Downloads, second.Uploads,
                totalDownloads = first.Downloads + second.Downloads,
                totalUploads = first.Uploads + second.Uploads,
            },
        };
        var manifestPath = Path.Combine(output, "activity.json");
        await using (var manifest = new FileStream(manifestPath, FileMode.CreateNew, FileAccess.Write))
        {
            await JsonSerializer.SerializeAsync(manifest, evidence, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
        }
        testOutput.WriteLine($"IFW_ACTIVITY_SHA256={ActivitySha256(manifestPath)}");
        if (rustBackupHash is not null) testOutput.WriteLine($"IFW_RUST_BACKUP_SHA256={rustBackupHash}");
    }

    private static async Task<string> ReceiveActivityBackupAsync(
        string exchangePath, string beforePath, string beforeHash, string afterPath, string afterHash, string restoredPath)
    {
        var directory = new DirectoryInfo(exchangePath);
        Assert.True(directory.Exists, "The coordinator must create the private exchange directory.");
        Assert.False(directory.Attributes.HasFlag(FileAttributes.ReparsePoint));
        if (!OperatingSystem.IsWindows())
        {
            const UnixFileMode others = UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute
                | UnixFileMode.OtherRead | UnixFileMode.OtherWrite | UnixFileMode.OtherExecute;
            Assert.Equal((UnixFileMode)0, File.GetUnixFileMode(directory.FullName) & others);
        }
        Assert.Empty(directory.EnumerateFileSystemInfos());
        using var exchange = SecureWatchRoot.Open(directory.FullName);
        File.Copy(beforePath, Path.Combine(directory.FullName, "before.db"));
        File.Copy(afterPath, Path.Combine(directory.FullName, "after.db"));
        var token = Guid.NewGuid().ToString("N");
        var request = new { format = "ifw-worker-backup-request-v1", token, beforeSha256 = beforeHash, afterSha256 = afterHash };
        var temporary = Path.Combine(directory.FullName, "request.tmp");
        await using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            await JsonSerializer.SerializeAsync(file, request);
        }
        File.Move(temporary, Path.Combine(directory.FullName, "request.json"));

        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(60));
        while (!exchange.FileExists("ready.json"))
        {
            if (deadline.IsCancellationRequested) throw new TimeoutException("The Rust backup did not publish ready.json within 60 seconds.");
            await Task.Delay(50);
        }
        var payload = await ReadExchangeFileAsync(exchange, "ready.json", 4096, deadline.Token);
        using var response = JsonDocument.Parse(payload);
        var fields = response.RootElement;
        Assert.Equal(["afterSha256", "format", "restoredSha256", "token"],
            fields.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal).ToArray());
        Assert.Equal("ifw-rust-worker-backup-ready-v1", fields.GetProperty("format").GetString());
        Assert.Equal(token, fields.GetProperty("token").GetString());
        Assert.Equal(afterHash, fields.GetProperty("afterSha256").GetString());
        var reported = fields.GetProperty("restoredSha256").GetString();
        Assert.Matches(@"\A[0-9a-f]{64}\z", reported);

        const int maxDatabaseBytes = 16 * 1024 * 1024;
        var returned = await ReadExchangeFileAsync(exchange, "returned.db", maxDatabaseBytes, deadline.Token);
        Assert.Equal(reported, Convert.ToHexStringLower(SHA256.HashData(returned)));
        await using (var restored = new FileStream(restoredPath, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            await restored.WriteAsync(returned, deadline.Token);
        }
        var consumed = ActivitySha256(restoredPath);
        Assert.Equal(reported, consumed);
        return consumed;
    }

    private static async Task<byte[]> ReadExchangeFileAsync(SecureWatchRoot exchange, string name, int maxBytes, CancellationToken token)
    {
        using var file = exchange.OpenRead(name);
        var length = file.Length;
        Assert.InRange(length, 1, maxBytes);
        var bytes = new byte[(int)length];
        await file.Stream.ReadExactlyAsync(bytes, token);
        Assert.Equal(0, await file.Stream.ReadAsync(new byte[1], token));
        Assert.Equal(length, file.Length);
        return bytes;
    }

    private sealed record ActivityWorkerRun(SyncStateEntry Entry, DateTimeOffset LastSuccess, int AlbumLists, int Downloads, int Uploads);

    private static async Task<ActivityWorkerRun> RunActivityWorkerAsync(
        AppConfig config, SqliteSyncStateStore store, string account, string? backupPath = null)
    {
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
        var logger = new InitialReconciliationLogger(WatchSourceSyncModes.Sync);
        using var worker = CreateWorker(config, store.DatabasePath, client, workerLogger: logger,
            syncStatusProvider: status, stateStore: store);
        SyncStateEntry entry;
        DateTimeOffset lastSuccess;
        await worker.StartAsync(CancellationToken.None);
        try
        {
            await logger.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
            await WaitUntilAsync(() => status.LastSyncCompletedUtc.HasValue, TimeSpan.FromSeconds(8));
            lastSuccess = Assert.IsType<DateTimeOffset>(status.LastSyncCompletedUtc);
            Assert.Equal(lastSuccess, await store.GetLastSuccessfulSyncAsync(account));
            entry = Assert.IsType<SyncStateEntry>(await store.GetAsync(account, config.Watch.Sources.Single().Path, "photo.jpg"));
            if (backupPath is not null) BackupActivityDatabase(store.DatabasePath, backupPath);
        }
        finally
        {
            await worker.StopAsync(CancellationToken.None);
        }
        Assert.NotEmpty(listedAlbums);
        Assert.All(listedAlbums, album => Assert.Equal("Camera", album));
        Assert.Null(status.LastSyncErrorMessage);
        Assert.Equal(0, logger.SyncPullFailureCount);
        Assert.All(client.DownloadedAssets, asset => Assert.Equal("remote", asset));
        return new(entry, lastSuccess, listedAlbums.Count, client.DownloadedAssets.Count, client.UploadCount);
    }

    private static SqliteConnection ActivityConnection(string path, SqliteOpenMode mode) =>
        new(new SqliteConnectionStringBuilder
        {
            DataSource = path, Mode = mode, Pooling = false,
        }.ToString());

    private static void BackupActivityDatabase(string sourcePath, string backupPath)
    {
        using var source = ActivityConnection(sourcePath, SqliteOpenMode.ReadOnly);
        source.Open();
        using (var destination = ActivityConnection(backupPath, SqliteOpenMode.ReadWriteCreate))
        {
            destination.Open();
            source.BackupDatabase(destination);
            using var command = destination.CreateCommand();
            command.CommandText = "PRAGMA journal_mode = DELETE";
            Assert.Equal("delete", command.ExecuteScalar());
        }
        Assert.False(File.Exists(backupPath + "-wal"));
        Assert.False(File.Exists(backupPath + "-shm"));
        Assert.False(File.Exists(backupPath + "-journal"));
    }

    private sealed record ActivityMapping(
        string AccountScope, string SourcePath, string SourceKey, string RelativePath, string RelativePathKey,
        string AssetId, string AlbumName, long FileSize, string LastWriteTimeUtc, int Direction, int Status,
        string LastSynchronizedAtUtc, string? TombstoneExpiresAtUtc);

    private static (List<ActivityMapping> Mappings, List<(string AccountScope, string LastSuccessfulSyncUtc)> Accounts)
        ReadActivityState(string path)
    {
        using var connection = ActivityConnection(path, SqliteOpenMode.ReadOnly);
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT account_scope, source_path, source_key, relative_path, relative_path_key,
                   asset_id, album_name, file_size, last_write_time_utc, direction, status,
                   last_synchronized_at_utc, tombstone_expires_at_utc FROM sync_entries;
            SELECT account_scope, last_successful_sync_utc FROM sync_account_status;
            SELECT (SELECT COUNT(*) FROM owned_albums), (SELECT COUNT(*) FROM sync_timestamp_repairs);
            """;
        using var reader = command.ExecuteReader();
        var mappings = new List<ActivityMapping>();
        while (reader.Read())
        {
            mappings.Add(new(reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetString(3),
                reader.GetString(4), reader.GetString(5), reader.GetString(6), reader.GetInt64(7),
                reader.GetString(8), reader.GetInt32(9), reader.GetInt32(10), reader.GetString(11),
                reader.IsDBNull(12) ? null : reader.GetString(12)));
        }
        Assert.True(reader.NextResult());
        var accounts = new List<(string, string)>();
        while (reader.Read()) accounts.Add((reader.GetString(0), reader.GetString(1)));
        Assert.True(reader.NextResult());
        Assert.True(reader.Read());
        Assert.Equal(0, reader.GetInt64(0));
        Assert.Equal(0, reader.GetInt64(1));
        return (mappings, accounts);
    }

    private sealed record ActivityFile(string Name, long Size, string Sha256, string LastWriteTimeUtc, string? CreationTimeUtc);

    private static ActivityFile ReadActivityFile(string path)
    {
        var bytes = File.ReadAllBytes(path);
        Assert.Equal("remote"u8.ToArray(), bytes);
        return new(Path.GetFileName(path), bytes.LongLength, Convert.ToHexStringLower(SHA256.HashData(bytes)),
            ActivityTimestamp(File.GetLastWriteTimeUtc(path)),
            OperatingSystem.IsWindows() ? ActivityTimestamp(File.GetCreationTimeUtc(path)) : null);
    }

    private static string ActivityTimestamp(DateTimeOffset value) => value.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture);

    private static string ActivityAssemblyVersion(Type type) =>
        Assert.IsType<AssemblyInformationalVersionAttribute>(type.Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>())
            .InformationalVersion;

    private static string ActivitySha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }
}
