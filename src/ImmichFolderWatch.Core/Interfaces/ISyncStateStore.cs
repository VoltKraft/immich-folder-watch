using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Interfaces;

public interface ISyncStateStore
{
    string DatabasePath { get; }

    Task InitializeAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Returns the account's most recent successful transfer in UTC, or null when no
    /// success is known. The summary survives deletion of individual synchronization entries.
    /// </summary>
    Task<DateTimeOffset?> GetLastSuccessfulSyncAsync(
        string accountScope,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Durably records a completed transfer for the account. Timestamps are normalized
    /// to UTC and an older completion cannot replace a newer one, including concurrent writes.
    /// Metadata-only entry updates must not call this method.
    /// </summary>
    Task RecordSuccessfulSyncAsync(
        string accountScope,
        DateTimeOffset completedUtc,
        CancellationToken cancellationToken = default);

    Task<SyncStateEntry?> GetAsync(
        string accountScope,
        string sourcePath,
        string relativePath,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<SyncStateEntry>> GetSourceEntriesAsync(
        string accountScope,
        string sourcePath,
        CancellationToken cancellationToken = default);

    Task UpsertAsync(SyncStateEntry entry, CancellationToken cancellationToken = default);

    Task<bool> DeleteAsync(
        string accountScope,
        string sourcePath,
        string relativePath,
        CancellationToken cancellationToken = default);

    Task<int> DeleteExpiredTombstonesAsync(
        DateTimeOffset utcNow,
        CancellationToken cancellationToken = default);
}
