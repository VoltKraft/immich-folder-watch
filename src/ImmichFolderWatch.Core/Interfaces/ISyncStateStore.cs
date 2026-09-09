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

    /// <summary>
    /// Persists repair intent before modifying the file. Repeating the same repair is
    /// idempotent; a different pending repair for the same file throws InvalidOperationException.
    /// </summary>
    Task SaveTimestampRepairAsync(SyncTimestampRepair repair, CancellationToken cancellationToken = default);

    /// <summary>Returns pending repairs for one account and normalized source path.</summary>
    Task<IReadOnlyList<SyncTimestampRepair>> GetTimestampRepairsAsync(
        string accountScope, string sourcePath, CancellationToken cancellationToken = default);

    /// <summary>
    /// Atomically updates the mapping and deletes matching repair intent. A non-null entry
    /// must have the same identity (otherwise ArgumentException), and the stored mapping
    /// must still equal OriginalEntry. Changed mappings or intent throw InvalidOperationException
    /// and leave both records unchanged. Null only deletes matching intent. Missing intent is
    /// an idempotent no-op. This never records a transfer success.
    /// </summary>
    Task CompleteTimestampRepairAsync(
        SyncTimestampRepair repair, SyncStateEntry? updatedEntry, CancellationToken cancellationToken = default);


    Task<bool> DeleteAsync(
        string accountScope,
        string sourcePath,
        string relativePath,
        CancellationToken cancellationToken = default);

    Task<int> DeleteExpiredTombstonesAsync(
        DateTimeOffset utcNow,
        CancellationToken cancellationToken = default);
}
