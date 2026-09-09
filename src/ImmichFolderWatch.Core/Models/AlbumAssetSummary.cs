namespace ImmichFolderWatch.Core.Models;

/// <param name="FileModifiedAt">Remote modification time, falling back to creation/upload time; null if unavailable.</param>
/// <param name="FileCreatedAt">Original file creation time reported by Immich; null when unavailable. Never inferred from server upload time.</param>
public sealed record AlbumAssetSummary(
    string Id,
    string OriginalFileName,
    DateTimeOffset? FileModifiedAt = null,
    DateTimeOffset? FileCreatedAt = null);
