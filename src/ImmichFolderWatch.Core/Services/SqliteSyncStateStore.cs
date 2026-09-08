using System.Globalization;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Platform;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Core.Services;

public sealed class SqliteSyncStateStore : ISyncStateStore
{
    private const int CurrentSchemaVersion = 1;
    private const int SqliteCorrupt = 11;
    private const int SqliteNotADatabase = 26;

    private readonly ILogger<SqliteSyncStateStore> _logger;
    private readonly bool _pathsCaseSensitive;
    private readonly SemaphoreSlim _initializationLock = new(1, 1);
    private volatile bool _initialized;

    public SqliteSyncStateStore(
        IPlatformPaths platformPaths,
        ILogger<SqliteSyncStateStore> logger)
        : this(platformPaths?.GetSyncDatabasePath() ?? throw new ArgumentNullException(nameof(platformPaths)), logger)
    {
    }

    public SqliteSyncStateStore(string databasePath)
        : this(databasePath, NullLogger<SqliteSyncStateStore>.Instance)
    {
    }

    public SqliteSyncStateStore(
        string databasePath,
        ILogger<SqliteSyncStateStore> logger,
        bool? pathsCaseSensitive = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(databasePath);
        DatabasePath = Path.GetFullPath(databasePath);
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _pathsCaseSensitive = pathsCaseSensitive ?? !OperatingSystem.IsWindows();
    }

    public string DatabasePath { get; }

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        if (_initialized)
        {
            return;
        }

        await _initializationLock.WaitAsync(cancellationToken);
        try
        {
            if (_initialized)
            {
                return;
            }

            var directory = Path.GetDirectoryName(DatabasePath);
            if (string.IsNullOrWhiteSpace(directory))
            {
                throw new InvalidOperationException($"The sync database path has no parent directory: {DatabasePath}");
            }

            Directory.CreateDirectory(directory);

            try
            {
                await InitializeCoreAsync(cancellationToken);
            }
            catch (SqliteException ex) when (IsCorruptDatabase(ex) && File.Exists(DatabasePath))
            {
                var quarantinePath = QuarantineCorruptDatabase();
                _logger.LogWarning(
                    ex,
                    "The synchronization database was corrupt and was moved to {QuarantinePath}. A new database will be created.",
                    quarantinePath);
                await InitializeCoreAsync(cancellationToken);
            }

            _initialized = true;
        }
        finally
        {
            _initializationLock.Release();
        }
    }

    public async Task<DateTimeOffset?> GetLastSuccessfulSyncAsync(
        string accountScope,
        CancellationToken cancellationToken = default)
    {
        ValidateAccountScope(accountScope);
        await InitializeAsync(cancellationToken);

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT last_successful_sync_utc
            FROM sync_account_status
            WHERE account_scope = $account_scope;
            """;
        command.Parameters.AddWithValue("$account_scope", accountScope);
        var value = await command.ExecuteScalarAsync(cancellationToken);
        return value is string timestamp ? FromDatabaseTimestamp(timestamp) : null;
    }

    public async Task RecordSuccessfulSyncAsync(
        string accountScope,
        DateTimeOffset completedUtc,
        CancellationToken cancellationToken = default)
    {
        ValidateAccountScope(accountScope);
        await InitializeAsync(cancellationToken);

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        // Fixed-width UTC roundtrip timestamps have chronological text ordering.
        // A single upsert also prevents concurrent completions from moving time backwards.
        command.CommandText = """
            INSERT INTO sync_account_status (account_scope, last_successful_sync_utc)
            VALUES ($account_scope, $completed_utc)
            ON CONFLICT(account_scope) DO UPDATE SET
                last_successful_sync_utc = MAX(
                    sync_account_status.last_successful_sync_utc,
                    excluded.last_successful_sync_utc);
            """;
        command.Parameters.AddWithValue("$account_scope", accountScope);
        command.Parameters.AddWithValue("$completed_utc", ToDatabaseTimestamp(completedUtc));
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task<SyncStateEntry?> GetAsync(
        string accountScope,
        string sourcePath,
        string relativePath,
        CancellationToken cancellationToken = default)
    {
        ValidateAccountScope(accountScope);
        var normalizedSourcePath = NormalizeSourcePath(sourcePath);
        var normalizedRelativePath = NormalizeRelativePath(relativePath);
        await InitializeAsync(cancellationToken);

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT account_scope, source_path, relative_path, asset_id, album_name,
                   file_size, last_write_time_utc, direction, status,
                   last_synchronized_at_utc, tombstone_expires_at_utc
            FROM sync_entries
            WHERE account_scope = $account_scope
              AND source_key = $source_key
              AND relative_path_key = $relative_path_key;
            """;
        command.Parameters.AddWithValue("$account_scope", accountScope);
        command.Parameters.AddWithValue("$source_key", GetPathKey(normalizedSourcePath));
        command.Parameters.AddWithValue("$relative_path_key", GetPathKey(normalizedRelativePath));

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken) ? ReadEntry(reader) : null;
    }

    public async Task<IReadOnlyList<SyncStateEntry>> GetSourceEntriesAsync(
        string accountScope,
        string sourcePath,
        CancellationToken cancellationToken = default)
    {
        ValidateAccountScope(accountScope);
        var normalizedSourcePath = NormalizeSourcePath(sourcePath);
        await InitializeAsync(cancellationToken);

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT account_scope, source_path, relative_path, asset_id, album_name,
                   file_size, last_write_time_utc, direction, status,
                   last_synchronized_at_utc, tombstone_expires_at_utc
            FROM sync_entries
            WHERE account_scope = $account_scope AND source_key = $source_key
            ORDER BY relative_path_key;
            """;
        command.Parameters.AddWithValue("$account_scope", accountScope);
        command.Parameters.AddWithValue("$source_key", GetPathKey(normalizedSourcePath));

        var entries = new List<SyncStateEntry>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            entries.Add(ReadEntry(reader));
        }

        return entries;
    }

    public async Task UpsertAsync(SyncStateEntry entry, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(entry);
        ValidateEntry(entry);
        var normalizedSourcePath = NormalizeSourcePath(entry.SourcePath);
        var normalizedRelativePath = NormalizeRelativePath(entry.RelativePath);
        await InitializeAsync(cancellationToken);

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.Transaction = (SqliteTransaction)transaction;
        command.CommandText = """
            INSERT INTO sync_entries (
                account_scope, source_path, source_key, relative_path, relative_path_key,
                asset_id, album_name, file_size, last_write_time_utc, direction, status,
                last_synchronized_at_utc, tombstone_expires_at_utc)
            VALUES (
                $account_scope, $source_path, $source_key, $relative_path, $relative_path_key,
                $asset_id, $album_name, $file_size, $last_write_time_utc, $direction, $status,
                $last_synchronized_at_utc, $tombstone_expires_at_utc)
            ON CONFLICT(account_scope, source_key, relative_path_key) DO UPDATE SET
                source_path = excluded.source_path,
                relative_path = excluded.relative_path,
                asset_id = excluded.asset_id,
                album_name = excluded.album_name,
                file_size = excluded.file_size,
                last_write_time_utc = excluded.last_write_time_utc,
                direction = excluded.direction,
                status = excluded.status,
                last_synchronized_at_utc = excluded.last_synchronized_at_utc,
                tombstone_expires_at_utc = excluded.tombstone_expires_at_utc;
            """;
        command.Parameters.AddWithValue("$account_scope", entry.AccountScope);
        command.Parameters.AddWithValue("$source_path", normalizedSourcePath);
        command.Parameters.AddWithValue("$source_key", GetPathKey(normalizedSourcePath));
        command.Parameters.AddWithValue("$relative_path", normalizedRelativePath);
        command.Parameters.AddWithValue("$relative_path_key", GetPathKey(normalizedRelativePath));
        command.Parameters.AddWithValue("$asset_id", (object?)entry.AssetId ?? DBNull.Value);
        command.Parameters.AddWithValue("$album_name", entry.AlbumName);
        command.Parameters.AddWithValue("$file_size", entry.FileSize);
        command.Parameters.AddWithValue("$last_write_time_utc", ToDatabaseTimestamp(entry.LastWriteTimeUtc));
        command.Parameters.AddWithValue("$direction", (int)entry.Direction);
        command.Parameters.AddWithValue("$status", (int)entry.Status);
        command.Parameters.AddWithValue("$last_synchronized_at_utc", ToDatabaseTimestamp(entry.LastSynchronizedAtUtc));
        command.Parameters.AddWithValue(
            "$tombstone_expires_at_utc",
            entry.TombstoneExpiresAtUtc is { } expiresAt
                ? ToDatabaseTimestamp(expiresAt)
                : DBNull.Value);

        await command.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<bool> DeleteAsync(
        string accountScope,
        string sourcePath,
        string relativePath,
        CancellationToken cancellationToken = default)
    {
        ValidateAccountScope(accountScope);
        var normalizedSourcePath = NormalizeSourcePath(sourcePath);
        var normalizedRelativePath = NormalizeRelativePath(relativePath);
        await InitializeAsync(cancellationToken);

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = """
            DELETE FROM sync_entries
            WHERE account_scope = $account_scope
              AND source_key = $source_key
              AND relative_path_key = $relative_path_key;
            """;
        command.Parameters.AddWithValue("$account_scope", accountScope);
        command.Parameters.AddWithValue("$source_key", GetPathKey(normalizedSourcePath));
        command.Parameters.AddWithValue("$relative_path_key", GetPathKey(normalizedRelativePath));
        return await command.ExecuteNonQueryAsync(cancellationToken) > 0;
    }

    public async Task<int> DeleteExpiredTombstonesAsync(
        DateTimeOffset utcNow,
        CancellationToken cancellationToken = default)
    {
        await InitializeAsync(cancellationToken);

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = """
            DELETE FROM sync_entries
            WHERE status = $tombstone_status
              AND tombstone_expires_at_utc IS NOT NULL
              AND tombstone_expires_at_utc <= $utc_now;
            """;
        command.Parameters.AddWithValue("$tombstone_status", (int)SyncEntryStatus.Tombstone);
        command.Parameters.AddWithValue("$utc_now", ToDatabaseTimestamp(utcNow));
        return await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private async Task InitializeCoreAsync(CancellationToken cancellationToken)
    {
        await using var connection = await OpenConnectionAsync(cancellationToken);

        await using (var versionCommand = connection.CreateCommand())
        {
            versionCommand.CommandText = "PRAGMA user_version;";
            var version = Convert.ToInt32(
                await versionCommand.ExecuteScalarAsync(cancellationToken),
                CultureInfo.InvariantCulture);
            if (version > CurrentSchemaVersion)
            {
                throw new NotSupportedException(
                    $"The synchronization database schema version {version} is newer than the supported version {CurrentSchemaVersion}.");
            }
        }

        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using var schemaCommand = connection.CreateCommand();
        schemaCommand.Transaction = (SqliteTransaction)transaction;
        schemaCommand.CommandText = """
            CREATE TABLE IF NOT EXISTS sync_entries (
                account_scope TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_key TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                relative_path_key TEXT NOT NULL,
                asset_id TEXT NULL,
                album_name TEXT NOT NULL,
                file_size INTEGER NOT NULL CHECK (file_size >= 0),
                last_write_time_utc TEXT NOT NULL,
                direction INTEGER NOT NULL CHECK (direction IN (0, 1)),
                status INTEGER NOT NULL CHECK (status IN (0, 1)),
                last_synchronized_at_utc TEXT NOT NULL,
                tombstone_expires_at_utc TEXT NULL,
                PRIMARY KEY (account_scope, source_key, relative_path_key),
                CHECK (
                    (status = 0 AND tombstone_expires_at_utc IS NULL)
                    OR (status = 1 AND tombstone_expires_at_utc IS NOT NULL)
                )
            );

            CREATE INDEX IF NOT EXISTS ix_sync_entries_asset_id
                ON sync_entries (account_scope, asset_id)
                WHERE asset_id IS NOT NULL;

            PRAGMA user_version = 1;
            """;
        await schemaCommand.ExecuteNonQueryAsync(cancellationToken);

        // This optional table leaves schema v1 readable by older binaries. Its creation
        // and historical backfill are atomic, so later metadata updates never get replayed
        // as transfer successes when the database is reopened.
        await using var summaryExistsCommand = connection.CreateCommand();
        summaryExistsCommand.Transaction = (SqliteTransaction)transaction;
        summaryExistsCommand.CommandText = """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'table' AND name = 'sync_account_status';
            """;
        var summaryExists = Convert.ToInt64(
            await summaryExistsCommand.ExecuteScalarAsync(cancellationToken),
            CultureInfo.InvariantCulture) != 0;
        if (!summaryExists)
        {
            await using var summaryCommand = connection.CreateCommand();
            summaryCommand.Transaction = (SqliteTransaction)transaction;
            summaryCommand.CommandText = """
                CREATE TABLE sync_account_status (
                    account_scope TEXT NOT NULL PRIMARY KEY,
                    last_successful_sync_utc TEXT NOT NULL
                );

                INSERT INTO sync_account_status (account_scope, last_successful_sync_utc)
                SELECT account_scope, MAX(last_synchronized_at_utc)
                FROM sync_entries
                WHERE status = $synchronized_status
                GROUP BY account_scope;
                """;
            summaryCommand.Parameters.AddWithValue("$synchronized_status", (int)SyncEntryStatus.Synchronized);
            await summaryCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
    }

    private async Task<SqliteConnection> OpenConnectionAsync(CancellationToken cancellationToken)
    {
        var builder = new SqliteConnectionStringBuilder
        {
            DataSource = DatabasePath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Cache = SqliteCacheMode.Shared,
            Pooling = true,
        };
        var connection = new SqliteConnection(builder.ToString());

        try
        {
            await connection.OpenAsync(cancellationToken);
            await using var command = connection.CreateCommand();
            command.CommandText = "PRAGMA busy_timeout = 5000; PRAGMA journal_mode = WAL;";
            await command.ExecuteNonQueryAsync(cancellationToken);
            return connection;
        }
        catch
        {
            await connection.DisposeAsync();
            throw;
        }
    }

    private string QuarantineCorruptDatabase()
    {
        SqliteConnection.ClearAllPools();
        var timestamp = DateTimeOffset.UtcNow.ToString("yyyyMMddTHHmmssfffZ", CultureInfo.InvariantCulture);
        var quarantinePath = $"{DatabasePath}.corrupt-{timestamp}";
        File.Move(DatabasePath, quarantinePath);

        MoveSidecarIfPresent($"{DatabasePath}-wal", $"{quarantinePath}-wal");
        MoveSidecarIfPresent($"{DatabasePath}-shm", $"{quarantinePath}-shm");
        return quarantinePath;
    }

    private static void MoveSidecarIfPresent(string sourcePath, string destinationPath)
    {
        if (File.Exists(sourcePath))
        {
            File.Move(sourcePath, destinationPath);
        }
    }

    private static bool IsCorruptDatabase(SqliteException exception) =>
        exception.SqliteErrorCode is SqliteCorrupt or SqliteNotADatabase;

    private static SyncStateEntry ReadEntry(SqliteDataReader reader) =>
        new(
            reader.GetString(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.IsDBNull(3) ? null : reader.GetString(3),
            reader.GetString(4),
            reader.GetInt64(5),
            FromDatabaseTimestamp(reader.GetString(6)),
            (SyncTransferDirection)reader.GetInt32(7),
            (SyncEntryStatus)reader.GetInt32(8),
            FromDatabaseTimestamp(reader.GetString(9)),
            reader.IsDBNull(10) ? null : FromDatabaseTimestamp(reader.GetString(10)));

    private static string ToDatabaseTimestamp(DateTimeOffset value) =>
        value.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture);

    private static DateTimeOffset FromDatabaseTimestamp(string value) =>
        DateTimeOffset.ParseExact(value, "O", CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind);

    private static void ValidateAccountScope(string accountScope)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(accountScope);
    }

    private static void ValidateEntry(SyncStateEntry entry)
    {
        ValidateAccountScope(entry.AccountScope);
        ArgumentException.ThrowIfNullOrWhiteSpace(entry.SourcePath);
        ArgumentException.ThrowIfNullOrWhiteSpace(entry.RelativePath);
        ArgumentNullException.ThrowIfNull(entry.AlbumName);

        if (entry.FileSize < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(entry), "File size cannot be negative.");
        }

        if (!Enum.IsDefined(entry.Direction))
        {
            throw new ArgumentOutOfRangeException(nameof(entry), "Transfer direction is invalid.");
        }

        if (!Enum.IsDefined(entry.Status))
        {
            throw new ArgumentOutOfRangeException(nameof(entry), "Synchronization status is invalid.");
        }

        if (entry.Status == SyncEntryStatus.Tombstone && entry.TombstoneExpiresAtUtc is null)
        {
            throw new ArgumentException("A tombstone must have an expiry timestamp.", nameof(entry));
        }

        if (entry.Status == SyncEntryStatus.Synchronized && entry.TombstoneExpiresAtUtc is not null)
        {
            throw new ArgumentException("A synchronized entry cannot have a tombstone expiry timestamp.", nameof(entry));
        }
    }

    private static string NormalizeSourcePath(string sourcePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourcePath);
        var fullPath = Path.GetFullPath(sourcePath);
        var root = Path.GetPathRoot(fullPath);
        return string.Equals(fullPath, root, StringComparison.Ordinal)
            ? fullPath
            : Path.TrimEndingDirectorySeparator(fullPath);
    }

    private static string NormalizeRelativePath(string relativePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(relativePath);
        if (Path.IsPathRooted(relativePath))
        {
            throw new ArgumentException("The stored file path must be relative to its watch source.", nameof(relativePath));
        }

        var normalized = relativePath.Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar)
            .TrimStart(Path.DirectorySeparatorChar);
        if (normalized.Length == 0)
        {
            throw new ArgumentException("The stored file path must identify a file.", nameof(relativePath));
        }

        return normalized;
    }

    private string GetPathKey(string path) =>
        _pathsCaseSensitive ? path : path.ToUpperInvariant();
}
