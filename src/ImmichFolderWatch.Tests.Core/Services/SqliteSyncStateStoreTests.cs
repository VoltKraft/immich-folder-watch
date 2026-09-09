using System.Text;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using Microsoft.Data.Sqlite;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class SqliteSyncStateStoreTests
{
    private static readonly DateTimeOffset FileTimestamp = new(2026, 8, 31, 12, 30, 0, TimeSpan.Zero);
    private static readonly DateTimeOffset SyncTimestamp = new(2026, 8, 31, 12, 31, 0, TimeSpan.Zero);

    [Fact]
    public async Task InitializeAsync_CreatesVersionedDatabase()
    {
        using var directory = new TemporaryDirectory();
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var store = new SqliteSyncStateStore(databasePath);

        await store.InitializeAsync();

        Assert.True(File.Exists(databasePath));
        await using var connection = new SqliteConnection($"Data Source={databasePath}");
        await connection.OpenAsync();
        await using var command = connection.CreateCommand();
        command.CommandText = "PRAGMA user_version;";
        Assert.Equal(1L, await command.ExecuteScalarAsync());
    }

    [Fact]
    public async Task InitializeAsync_MigratesExistingVersionZeroDatabase()
    {
        using var directory = new TemporaryDirectory();
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        await using (var connection = new SqliteConnection($"Data Source={databasePath}"))
        {
            await connection.OpenAsync();
            await using var command = connection.CreateCommand();
            command.CommandText = "CREATE TABLE legacy_marker (value TEXT); PRAGMA user_version = 0;";
            await command.ExecuteNonQueryAsync();
        }

        var store = new SqliteSyncStateStore(databasePath);
        await store.InitializeAsync();
        await store.UpsertAsync(CreateEntry(
            "scope",
            Path.Combine(directory.Path, "photos"),
            "photo.jpg",
            "asset"));

        await using var migrated = new SqliteConnection($"Data Source={databasePath}");
        await migrated.OpenAsync();
        await using var versionCommand = migrated.CreateCommand();
        versionCommand.CommandText = "PRAGMA user_version;";
        Assert.Equal(1L, await versionCommand.ExecuteScalarAsync());
        Assert.NotNull(await store.GetAsync(
            "scope",
            Path.Combine(directory.Path, "photos"),
            "photo.jpg"));
    }

    [Fact]
    public async Task RecordSuccessfulSyncAsync_PersistsAcrossStoreInstancesAndSeparatesAccounts()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        Assert.Null(await store.GetLastSuccessfulSyncAsync("scope-a"));

        await store.RecordSuccessfulSyncAsync("scope-a", SyncTimestamp);
        await store.RecordSuccessfulSyncAsync("scope-b", SyncTimestamp.AddHours(1));
        SqliteConnection.ClearAllPools();

        var reopened = CreateStore(directory);
        Assert.Equal(SyncTimestamp, await reopened.GetLastSuccessfulSyncAsync("scope-a"));
        Assert.Equal(SyncTimestamp.AddHours(1), await reopened.GetLastSuccessfulSyncAsync("scope-b"));
        Assert.Null(await reopened.GetLastSuccessfulSyncAsync("unknown"));
    }

    [Fact]
    public async Task RecordSuccessfulSyncAsync_NormalizesOffsetsAndNeverMovesBackwards()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var latest = SyncTimestamp.AddTicks(1);

        await store.RecordSuccessfulSyncAsync("scope", SyncTimestamp.ToOffset(TimeSpan.FromHours(12)));
        await store.RecordSuccessfulSyncAsync("scope", latest.ToOffset(TimeSpan.FromHours(-10)));
        await store.RecordSuccessfulSyncAsync("scope", SyncTimestamp.ToOffset(TimeSpan.FromHours(14)));

        var actual = await CreateStore(directory).GetLastSuccessfulSyncAsync("scope");
        Assert.Equal(latest, actual);
        Assert.Equal(TimeSpan.Zero, actual!.Value.Offset);
    }

    [Fact]
    public async Task RecordSuccessfulSyncAsync_ConcurrentStoresKeepLatestCompletion()
    {
        using var directory = new TemporaryDirectory();
        var first = CreateStore(directory);
        var second = CreateStore(directory);
        await first.InitializeAsync();
        await second.InitializeAsync();

        await Task.WhenAll(
            Task.Run(() => first.RecordSuccessfulSyncAsync("scope", SyncTimestamp.AddSeconds(2))),
            Task.Run(() => second.RecordSuccessfulSyncAsync("scope", SyncTimestamp)),
            Task.Run(() => first.RecordSuccessfulSyncAsync("scope", SyncTimestamp.AddSeconds(1))));

        Assert.Equal(SyncTimestamp.AddSeconds(2), await second.GetLastSuccessfulSyncAsync("scope"));
    }

    [Fact]
    public async Task LastSuccessfulSync_SurvivesEntryDeletionAndTombstoneExpiry()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var source = Path.Combine(directory.Path, "photos");
        await store.UpsertAsync(CreateEntry("scope", source, "photo.jpg", "asset-1"));
        await store.RecordSuccessfulSyncAsync("scope", SyncTimestamp);
        await store.UpsertAsync(CreateEntry("scope", source, "deleted.jpg", "asset-2") with
        {
            Status = SyncEntryStatus.Tombstone,
            LastSynchronizedAtUtc = SyncTimestamp.AddDays(1),
            TombstoneExpiresAtUtc = SyncTimestamp.AddDays(2),
        });

        Assert.True(await store.DeleteAsync("scope", source, "photo.jpg"));
        Assert.Equal(1, await store.DeleteExpiredTombstonesAsync(SyncTimestamp.AddDays(3)));

        var reopened = CreateStore(directory);
        Assert.Empty(await reopened.GetSourceEntriesAsync("scope", source));
        Assert.Equal(SyncTimestamp, await reopened.GetLastSuccessfulSyncAsync("scope"));
    }

    [Fact]
    public async Task UpsertAsync_MetadataUpdatesDoNotRecordOrAdvanceSuccessfulSync()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var entry = CreateEntry("scope", Path.Combine(directory.Path, "photos"), "photo.jpg", "asset");
        await store.UpsertAsync(entry);
        Assert.Null(await CreateStore(directory).GetLastSuccessfulSyncAsync("scope"));

        await store.RecordSuccessfulSyncAsync("scope", SyncTimestamp);
        await store.UpsertAsync(entry with
        {
            AlbumName = "Renamed album",
            LastSynchronizedAtUtc = SyncTimestamp.AddDays(1),
        });

        Assert.Equal(SyncTimestamp, await CreateStore(directory).GetLastSuccessfulSyncAsync("scope"));
    }

    [Fact]
    public async Task InitializeAsync_BackfillsVersionOneHistoryOnceWithoutTombstones()
    {
        using var directory = new TemporaryDirectory();
        var legacy = CreateStore(directory);
        var source = Path.Combine(directory.Path, "photos");
        var newestEntry = CreateEntry("scope-a", source, "new.jpg", "asset-new") with
        {
            LastSynchronizedAtUtc = SyncTimestamp.AddHours(1),
        };
        await legacy.UpsertAsync(CreateEntry("scope-a", source, "old.jpg", "asset-old"));
        await legacy.UpsertAsync(newestEntry);
        await legacy.UpsertAsync(CreateEntry("scope-b", source, "other.jpg", "asset-other"));
        foreach (var account in new[] { "scope-a", "tombstones-only" })
        {
            await legacy.UpsertAsync(CreateEntry(account, source, "deleted.jpg", "asset-deleted") with
            {
                Status = SyncEntryStatus.Tombstone,
                LastSynchronizedAtUtc = SyncTimestamp.AddDays(1),
                TombstoneExpiresAtUtc = SyncTimestamp.AddDays(2),
            });
        }

        // Reproduce the pre-extension v1 database: the base table and its rows are unchanged.
        await using (var connection = new SqliteConnection($"Data Source={legacy.DatabasePath}"))
        {
            await connection.OpenAsync();
            await using var command = connection.CreateCommand();
            command.CommandText = "DROP TABLE sync_account_status; PRAGMA user_version;";
            Assert.Equal(1L, await command.ExecuteScalarAsync());
        }

        var upgraded = CreateStore(directory);
        Assert.Equal(newestEntry.LastSynchronizedAtUtc, await upgraded.GetLastSuccessfulSyncAsync("scope-a"));
        Assert.Equal(SyncTimestamp, await upgraded.GetLastSuccessfulSyncAsync("scope-b"));
        Assert.Null(await upgraded.GetLastSuccessfulSyncAsync("tombstones-only"));
        Assert.Equal(3, (await upgraded.GetSourceEntriesAsync("scope-a", source)).Count);

        await upgraded.UpsertAsync(newestEntry with { LastSynchronizedAtUtc = SyncTimestamp.AddDays(3) });
        await upgraded.UpsertAsync(CreateEntry("new-account", source, "metadata.jpg", "asset-metadata"));
        var reopened = CreateStore(directory);
        Assert.Equal(newestEntry.LastSynchronizedAtUtc, await reopened.GetLastSuccessfulSyncAsync("scope-a"));
        Assert.Null(await reopened.GetLastSuccessfulSyncAsync("new-account"));
        await using var migrated = new SqliteConnection($"Data Source={legacy.DatabasePath}");
        await migrated.OpenAsync();
        await using var versionCommand = migrated.CreateCommand();
        versionCommand.CommandText = "PRAGMA user_version;";
        Assert.Equal(1L, await versionCommand.ExecuteScalarAsync());
    }

    [Fact]
    public async Task InitializeAsync_RefusesNewerVersionWithoutCreatingSummary()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        await using var connection = new SqliteConnection($"Data Source={store.DatabasePath}");
        await connection.OpenAsync();
        await using var command = connection.CreateCommand();
        command.CommandText = "PRAGMA user_version = 2;";
        await command.ExecuteNonQueryAsync();

        await Assert.ThrowsAsync<NotSupportedException>(() => store.InitializeAsync());

        command.CommandText = "SELECT COUNT(*) FROM sqlite_master WHERE name = 'sync_account_status';";
        Assert.Equal(0L, await command.ExecuteScalarAsync());
        command.CommandText = "PRAGMA user_version;";
        Assert.Equal(2L, await command.ExecuteScalarAsync());
    }

    [Fact]
    public async Task UpsertAsync_RoundTripsAndUpdatesEntry()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var entry = CreateEntry("scope-a", Path.Combine(directory.Path, "photos"), "2026/photo.jpg", "asset-1");

        await store.UpsertAsync(entry);
        await store.UpsertAsync(entry with { AssetId = "asset-2", AlbumName = "Updated album" });

        var actual = await store.GetAsync(entry.AccountScope, entry.SourcePath, entry.RelativePath);
        Assert.NotNull(actual);
        Assert.Equal("asset-2", actual.AssetId);
        Assert.Equal("Updated album", actual.AlbumName);
        Assert.Equal(entry.FileSize, actual.FileSize);
        Assert.Equal(entry.LastWriteTimeUtc, actual.LastWriteTimeUtc);
        Assert.Equal(entry.LastSynchronizedAtUtc, actual.LastSynchronizedAtUtc);
    }

    [Fact]
    public async Task GetSourceEntriesAsync_UsesOneDatabaseButSeparatesSourcesAndAccounts()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var sourceA = Path.Combine(directory.Path, "source-a");
        var sourceB = Path.Combine(directory.Path, "source-b");
        await store.UpsertAsync(CreateEntry("scope-a", sourceA, "same.jpg", "asset-a"));
        await store.UpsertAsync(CreateEntry("scope-a", sourceB, "same.jpg", "asset-b"));
        await store.UpsertAsync(CreateEntry("scope-b", sourceA, "same.jpg", "asset-c"));

        var sourceAEntries = await store.GetSourceEntriesAsync("scope-a", sourceA);
        var sourceBEntries = await store.GetSourceEntriesAsync("scope-a", sourceB);

        Assert.Single(sourceAEntries);
        Assert.Equal("asset-a", sourceAEntries[0].AssetId);
        Assert.Single(sourceBEntries);
        Assert.Equal("asset-b", sourceBEntries[0].AssetId);
        Assert.Equal(Path.Combine(directory.Path, "sync-state.db"), store.DatabasePath);
    }

    [Fact]
    public async Task Paths_AreCaseInsensitive_WhenConfiguredForWindowsSemantics()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory, pathsCaseSensitive: false);
        var source = Path.Combine(directory.Path, "Photos");
        await store.UpsertAsync(CreateEntry("scope", source, "Folder/Photo.jpg", "asset"));

        var actual = await store.GetAsync("scope", source.ToUpperInvariant(), "FOLDER/PHOTO.JPG");

        Assert.NotNull(actual);
        Assert.Equal("asset", actual.AssetId);
    }

    [Fact]
    public async Task Paths_AreCaseSensitive_WhenConfiguredForLinuxSemantics()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory, pathsCaseSensitive: true);
        var source = Path.Combine(directory.Path, "Photos");
        await store.UpsertAsync(CreateEntry("scope", source, "Folder/Photo.jpg", "asset"));

        var actual = await store.GetAsync("scope", source, "Folder/photo.jpg");

        Assert.Null(actual);
    }

    [Fact]
    public async Task DeleteAsync_RemovesOnlyRequestedEntry()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var source = Path.Combine(directory.Path, "photos");
        await store.UpsertAsync(CreateEntry("scope", source, "one.jpg", "asset-1"));
        await store.UpsertAsync(CreateEntry("scope", source, "two.jpg", "asset-2"));

        var deleted = await store.DeleteAsync("scope", source, "one.jpg");

        Assert.True(deleted);
        Assert.Null(await store.GetAsync("scope", source, "one.jpg"));
        Assert.NotNull(await store.GetAsync("scope", source, "two.jpg"));
    }

    [Fact]
    public async Task DeleteExpiredTombstonesAsync_RemovesOnlyExpiredTombstones()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var source = Path.Combine(directory.Path, "photos");
        var now = new DateTimeOffset(2026, 9, 1, 10, 0, 0, TimeSpan.Zero);
        await store.UpsertAsync(CreateEntry("scope", source, "synced.jpg", "asset-1"));
        await store.UpsertAsync(CreateEntry("scope", source, "expired.jpg", "asset-2") with
        {
            Status = SyncEntryStatus.Tombstone,
            TombstoneExpiresAtUtc = now.AddSeconds(-1),
        });
        await store.UpsertAsync(CreateEntry("scope", source, "active.jpg", "asset-3") with
        {
            Status = SyncEntryStatus.Tombstone,
            TombstoneExpiresAtUtc = now.AddMinutes(1),
        });

        var deletedCount = await store.DeleteExpiredTombstonesAsync(now);

        Assert.Equal(1, deletedCount);
        Assert.Null(await store.GetAsync("scope", source, "expired.jpg"));
        Assert.NotNull(await store.GetAsync("scope", source, "active.jpg"));
        Assert.NotNull(await store.GetAsync("scope", source, "synced.jpg"));
    }

    [Fact]
    public async Task InitializeAsync_QuarantinesInvalidDatabaseAndCreatesReplacement()
    {
        using var directory = new TemporaryDirectory();
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        await File.WriteAllTextAsync(databasePath, "not a sqlite database");
        var store = new SqliteSyncStateStore(databasePath);

        await store.InitializeAsync();

        Assert.True(File.Exists(databasePath));
        Assert.Single(Directory.GetFiles(directory.Path, "sync-state.db.corrupt-*"));
        await store.UpsertAsync(CreateEntry("scope", Path.Combine(directory.Path, "photos"), "photo.jpg", "asset"));
    }

    [Fact]
    public async Task Database_DoesNotContainApiKey()
    {
        using var directory = new TemporaryDirectory();
        const string apiKey = "secret-api-key-that-must-not-be-persisted";
        var accountScope = SyncAccountScope.Create("https://photos.example/api/", apiKey);
        var store = CreateStore(directory);
        await store.UpsertAsync(CreateEntry(
            accountScope,
            Path.Combine(directory.Path, "photos"),
            "photo.jpg",
            "asset"));

        SqliteConnection.ClearAllPools();
        var persistedBytes = Directory.GetFiles(directory.Path, "sync-state.db*")
            .SelectMany(File.ReadAllBytes)
            .ToArray();
        var persistedText = Encoding.UTF8.GetString(persistedBytes);

        Assert.DoesNotContain(apiKey, persistedText, StringComparison.Ordinal);
        Assert.Equal(64, accountScope.Length);
    }

    [Fact]
    public void SyncAccountScope_NormalizesTrailingServerUrlSlash()
    {
        var withoutSlash = SyncAccountScope.Create("https://photos.example/api", "key");
        var withSlash = SyncAccountScope.Create(" https://photos.example/api/ ", "key");

        Assert.Equal(withoutSlash, withSlash);
    }

    [Fact]
    public async Task TimestampRepairs_PersistAcrossReopenAndRespectAccountSourceAndPathCase()
    {
        using var directory = new TemporaryDirectory();
        var source = Path.Combine(directory.Path, "Photos");
        var store = CreateStore(directory, pathsCaseSensitive: false);
        var entry = CreateEntry("scope-a", source + Path.DirectorySeparatorChar, "Photo.jpg", "asset");
        var repair = new SyncTimestampRepair(entry, FileTimestamp.AddDays(-1), FileTimestamp, new string('a', 64));
        await store.SaveTimestampRepairAsync(repair);
        await store.SaveTimestampRepairAsync(repair with { OriginalEntry = entry with { SourcePath = source.ToUpperInvariant(), RelativePath = "PHOTO.JPG" } });
        await store.SaveTimestampRepairAsync(repair with { OriginalEntry = entry with { AccountScope = "scope-b" } });
        await store.SaveTimestampRepairAsync(repair with { OriginalEntry = entry with { SourcePath = source + "Other" } });
        SqliteConnection.ClearAllPools();
        var reopened = CreateStore(directory, pathsCaseSensitive: false);
        var actual = Assert.Single(await reopened.GetTimestampRepairsAsync("scope-a", source.ToLowerInvariant()));
        Assert.Equal(Path.TrimEndingDirectorySeparator(source), actual.OriginalEntry.SourcePath);
        Assert.Equal(repair.CreationTimeUtc, actual.CreationTimeUtc);
        Assert.Equal(new string('A', 64), actual.ContentSha256);
        Assert.Single(await reopened.GetTimestampRepairsAsync("scope-b", source));
        Assert.Empty(await reopened.GetTimestampRepairsAsync("unknown", source));
        Assert.Empty(await reopened.GetTimestampRepairsAsync("scope-a", source + "missing"));
        Assert.Empty(await CreateStore(directory, pathsCaseSensitive: true).GetTimestampRepairsAsync("scope-a", source.ToLowerInvariant()));
    }

    [Fact]
    public async Task CompleteTimestampRepairAsync_UpdatesMappingAndRemovesJournalWithoutRecordingSuccess()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var entry = CreateEntry("scope", Path.Combine(directory.Path, "photos"), "photo.jpg", "asset");
        var repair = CreateRepair(entry);
        await store.UpsertAsync(entry);
        await store.RecordSuccessfulSyncAsync("scope", SyncTimestamp);
        await store.SaveTimestampRepairAsync(repair);
        var updated = entry with { LastWriteTimeUtc = repair.LastWriteTimeUtc };
        await store.CompleteTimestampRepairAsync(repair, updated);
        Assert.Equal(updated, await store.GetAsync("scope", entry.SourcePath, entry.RelativePath));
        Assert.Empty(await store.GetTimestampRepairsAsync("scope", entry.SourcePath));
        Assert.Equal(SyncTimestamp, await store.GetLastSuccessfulSyncAsync("scope"));
        await store.UpsertAsync(updated with { AssetId = "newer" });
        await store.CompleteTimestampRepairAsync(repair, updated);
        Assert.Equal("newer", (await store.GetAsync("scope", entry.SourcePath, entry.RelativePath))!.AssetId);
    }

    [Fact]
    public async Task CompleteTimestampRepairAsync_RejectsChangedMappingAndNullOnlyDiscardsIntent()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var entry = CreateEntry("scope", Path.Combine(directory.Path, "photos"), "photo.jpg", "asset");
        var repair = CreateRepair(entry);
        await store.UpsertAsync(entry);
        await store.SaveTimestampRepairAsync(repair);
        var changed = entry with { AssetId = "different-asset" };
        await store.UpsertAsync(changed);
        await Assert.ThrowsAsync<InvalidOperationException>(() => store.CompleteTimestampRepairAsync(repair, entry with { LastWriteTimeUtc = repair.LastWriteTimeUtc }));
        Assert.Single(await store.GetTimestampRepairsAsync("scope", entry.SourcePath));
        Assert.Equal(changed, await store.GetAsync("scope", entry.SourcePath, entry.RelativePath));
        await store.CompleteTimestampRepairAsync(repair, null);
        Assert.Empty(await store.GetTimestampRepairsAsync("scope", entry.SourcePath));
        Assert.Equal(changed, await store.GetAsync("scope", entry.SourcePath, entry.RelativePath));
    }

    [Fact]
    public async Task CompleteTimestampRepairAsync_RollsBackMappingWhenJournalDeleteFails()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var entry = CreateEntry("scope", Path.Combine(directory.Path, "photos"), "photo.jpg", "asset");
        var repair = CreateRepair(entry);
        await store.UpsertAsync(entry);
        await store.SaveTimestampRepairAsync(repair);
        await using (var connection = new SqliteConnection($"Data Source={store.DatabasePath}"))
        {
            await connection.OpenAsync();
            await using var command = connection.CreateCommand();
            command.CommandText = "CREATE TRIGGER reject_repair_delete BEFORE DELETE ON sync_timestamp_repairs BEGIN SELECT RAISE(ABORT, 'test journal failure'); END;";
            await command.ExecuteNonQueryAsync();
        }
        await Assert.ThrowsAsync<SqliteException>(() => store.CompleteTimestampRepairAsync(repair, entry with { LastWriteTimeUtc = repair.LastWriteTimeUtc }));
        Assert.Equal(entry, await store.GetAsync("scope", entry.SourcePath, entry.RelativePath));
        Assert.Single(await store.GetTimestampRepairsAsync("scope", entry.SourcePath));
    }

    [Fact]
    public async Task TimestampRepairs_RejectConflictingIntentAndMismatchedCompletionIdentity()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var entry = CreateEntry("scope", Path.Combine(directory.Path, "photos"), "photo.jpg", "asset");
        var repair = CreateRepair(entry);
        await store.SaveTimestampRepairAsync(repair);
        await Assert.ThrowsAsync<InvalidOperationException>(() => store.SaveTimestampRepairAsync(repair with { LastWriteTimeUtc = FileTimestamp.AddHours(2) }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => store.CompleteTimestampRepairAsync(repair with { LastWriteTimeUtc = FileTimestamp.AddHours(2) }, null));
        await Assert.ThrowsAsync<ArgumentException>(() => store.CompleteTimestampRepairAsync(repair, entry with { AccountScope = "other" }));
        Assert.Equal(repair, Assert.Single(await store.GetTimestampRepairsAsync("scope", entry.SourcePath)));
    }

    [Fact]
    public async Task SaveTimestampRepairAsync_RejectsInvalidContentFingerprint()
    {
        using var directory = new TemporaryDirectory();
        var store = CreateStore(directory);
        var repair = CreateRepair(CreateEntry("scope", directory.Path, "photo.jpg", "asset"));
        await Assert.ThrowsAsync<ArgumentException>(() => store.SaveTimestampRepairAsync(repair with { ContentSha256 = "not-a-hash" }));
        Assert.Empty(await store.GetTimestampRepairsAsync("scope", directory.Path));
    }

    private static SyncTimestampRepair CreateRepair(SyncStateEntry entry) =>
        new(entry, FileTimestamp.AddDays(-1), FileTimestamp.AddHours(-1), new string('A', 64));

    private static SqliteSyncStateStore CreateStore(
        TemporaryDirectory directory,
        bool? pathsCaseSensitive = null) =>
        new(
            Path.Combine(directory.Path, "sync-state.db"),
            Microsoft.Extensions.Logging.Abstractions.NullLogger<SqliteSyncStateStore>.Instance,
            pathsCaseSensitive);

    private static SyncStateEntry CreateEntry(
        string accountScope,
        string sourcePath,
        string relativePath,
        string assetId) =>
        new(
            accountScope,
            sourcePath,
            relativePath,
            assetId,
            "Camera",
            1234,
            FileTimestamp,
            SyncTransferDirection.Upload,
            SyncEntryStatus.Synchronized,
            SyncTimestamp);

    private sealed class TemporaryDirectory : IDisposable
    {
        public TemporaryDirectory()
        {
            Path = System.IO.Path.Combine(
                System.IO.Path.GetTempPath(),
                $"immich-folder-watch-tests-{Guid.NewGuid():N}");
            Directory.CreateDirectory(Path);
        }

        public string Path { get; }

        public void Dispose()
        {
            SqliteConnection.ClearAllPools();
            Directory.Delete(Path, recursive: true);
        }
    }
}
