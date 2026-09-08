namespace ImmichFolderWatch.Core.Models;

/// <param name="FileModifiedAt">Remote modification time, falling back to creation/upload time; null if unavailable.</param>
public sealed record AlbumAssetSummary(string Id, string OriginalFileName, DateTimeOffset? FileModifiedAt = null);
