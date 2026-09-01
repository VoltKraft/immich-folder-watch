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
