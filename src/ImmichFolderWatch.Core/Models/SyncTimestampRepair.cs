namespace ImmichFolderWatch.Core.Models;

/// <summary>
/// Durable intent to repair local timestamps without changing the synchronized content.
/// OriginalEntry identifies the expected mapping; ContentSha256 is the hexadecimal SHA-256
/// of the verified local content. Recovery must verify it before applying the timestamps.
/// </summary>
public sealed record SyncTimestampRepair(
    SyncStateEntry OriginalEntry,
    DateTimeOffset CreationTimeUtc,
    DateTimeOffset LastWriteTimeUtc,
    string ContentSha256);
