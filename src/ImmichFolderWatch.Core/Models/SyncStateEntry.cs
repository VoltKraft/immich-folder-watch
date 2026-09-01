namespace ImmichFolderWatch.Core.Models;

public sealed record SyncStateEntry(
    string AccountScope,
    string SourcePath,
    string RelativePath,
    string? AssetId,
    string AlbumName,
    long FileSize,
    DateTimeOffset LastWriteTimeUtc,
    SyncTransferDirection Direction,
    SyncEntryStatus Status,
    DateTimeOffset LastSynchronizedAtUtc,
    DateTimeOffset? TombstoneExpiresAtUtc = null);

public enum SyncTransferDirection
{
    Upload = 0,
    Download = 1,
}

public enum SyncEntryStatus
{
    Synchronized = 0,
    Tombstone = 1,
}
