using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

public sealed class UploadBatchQueue : IUploadBatchQueue
{
    private static readonly StringComparer PathComparer = OperatingSystem.IsWindows()
        ? StringComparer.OrdinalIgnoreCase
        : StringComparer.Ordinal;

    private readonly object _gate = new();

    private readonly Dictionary<string, QueuedUpload> _queuedPaths = new(PathComparer);

    private long _nextSequence;

    public int Count
    {
        get
        {
            lock (_gate)
            {
                return _queuedPaths.Count;
            }
        }
    }

    public bool TryEnqueue(UploadAssetRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var normalizedPath = NormalizePath(request.FilePath);
        var normalizedSourcePath = string.IsNullOrWhiteSpace(request.SourcePath)
            ? string.Empty
            : NormalizePath(request.SourcePath);
        var normalizedRequest = request with
        {
            FilePath = normalizedPath,
            SourcePath = normalizedSourcePath,
        };

        var timestamp = GetLastWriteTimeUtc(normalizedPath);
        lock (_gate)
        {
            return _queuedPaths.TryAdd(normalizedPath, new QueuedUpload(normalizedRequest, timestamp, _nextSequence++));
        }
    }

    public IReadOnlyList<UploadAssetRequest> DequeueBatch(int maxBatchSize, string transferOrder = TransferOrders.NewestFirst)
    {
        if (maxBatchSize <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxBatchSize), "Batch size must be greater than zero.");
        }

        lock (_gate)
        {
            var datedFirst = _queuedPaths.Values
                .OrderBy(item => item.Request.Attempt > 1)
                .ThenBy(item => !item.LastWriteTimeUtc.HasValue);
            var ordered = TransferOrders.Normalize(transferOrder) == TransferOrders.OldestFirst
                ? datedFirst.ThenBy(item => item.LastWriteTimeUtc)
                : datedFirst.ThenByDescending(item => item.LastWriteTimeUtc);
            var batch = ordered.ThenBy(item => item.Sequence)
                .Take(maxBatchSize)
                .Select(item => item.Request)
                .ToList();
            foreach (var item in batch)
            {
                _queuedPaths.Remove(item.FilePath);
            }

            return batch;
        }
    }

    private static DateTime? GetLastWriteTimeUtc(string path)
    {
        try
        {
            var file = new FileInfo(path);
            return file.Exists ? file.LastWriteTimeUtc : null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            // A disappearing or inaccessible file must not prevent other files from being queued.
            return null;
        }
    }

    private sealed record QueuedUpload(UploadAssetRequest Request, DateTime? LastWriteTimeUtc, long Sequence);

    private static string NormalizePath(string path)
    {
        var trimmed = path.Trim();

        try
        {
            return Path.GetFullPath(trimmed);
        }
        catch (Exception)
        {
            return trimmed;
        }
    }
}
