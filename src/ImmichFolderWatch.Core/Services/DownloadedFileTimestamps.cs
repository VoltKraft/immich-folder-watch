using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

/// <summary>Filesystem timestamp values to apply before recording a downloaded file's fingerprint.</summary>
/// <param name="CreationTimeUtc">Original creation time, applied to the creation attribute on Windows.</param>
/// <param name="LastWriteTimeUtc">Modification time to apply; on Linux this represents original creation time.</param>
public sealed record DownloadedFileTimestampValues(DateTimeOffset CreationTimeUtc, DateTimeOffset LastWriteTimeUtc);

/// <summary>Maps original asset dates to writable filesystem attributes without changing file contents.</summary>
public static class DownloadedFileTimestamps
{
    /// <summary>
    /// Returns UTC values when Immich supplies an original creation date; otherwise returns null.
    /// Windows retains the remote modification date. Linux cannot set birth time, so the writable
    /// modification date represents original creation time for file-manager sorting.
    /// </summary>
    public static DownloadedFileTimestampValues? GetDesired(AlbumAssetSummary asset)
    {
        ArgumentNullException.ThrowIfNull(asset);
        if (asset.FileCreatedAt is not { } created)
        {
            return null;
        }

        var modified = OperatingSystem.IsWindows() ? asset.FileModifiedAt ?? created : created;
        return new DownloadedFileTimestampValues(created.ToUniversalTime(), modified.ToUniversalTime());
    }

    /// <summary>
    /// Updates an existing file's timestamps. On Linux only modification time is writable;
    /// Windows also receives its creation time. Does not create or modify file contents.
    /// </summary>
    /// <remarks>
    /// Filesystem and permission errors propagate. The two Windows writes are not atomic;
    /// callers must reconcile partial metadata changes before updating a persisted fingerprint.
    /// </remarks>
    public static void Apply(string path, DownloadedFileTimestampValues values)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        ArgumentNullException.ThrowIfNull(values);
        if (OperatingSystem.IsWindows())
        {
            File.SetCreationTimeUtc(path, values.CreationTimeUtc.UtcDateTime);
        }

        File.SetLastWriteTimeUtc(path, values.LastWriteTimeUtc.UtcDateTime);
    }
}
