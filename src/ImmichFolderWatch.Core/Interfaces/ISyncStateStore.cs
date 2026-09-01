using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Interfaces;

public interface ISyncStateStore
{
    string DatabasePath { get; }

    Task InitializeAsync(CancellationToken cancellationToken = default);

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
