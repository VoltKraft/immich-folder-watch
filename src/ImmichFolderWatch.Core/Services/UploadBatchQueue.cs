using System.Collections.Concurrent;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

public sealed class UploadBatchQueue : IUploadBatchQueue
{
    private static readonly StringComparer PathComparer = OperatingSystem.IsWindows()
        ? StringComparer.OrdinalIgnoreCase
        : StringComparer.Ordinal;

    private readonly ConcurrentQueue<UploadAssetRequest> _queue = new();

    private readonly ConcurrentDictionary<string, byte> _queuedPaths = new(PathComparer);

    public int Count => _queuedPaths.Count;

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

        if (!_queuedPaths.TryAdd(normalizedPath, 0))
        {
            return false;
        }

        _queue.Enqueue(normalizedRequest);
        return true;
    }

    public IReadOnlyList<UploadAssetRequest> DequeueBatch(int maxBatchSize)
    {
        if (maxBatchSize <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxBatchSize), "Batch size must be greater than zero.");
        }

        var batch = new List<UploadAssetRequest>(maxBatchSize);

        while (batch.Count < maxBatchSize && _queue.TryDequeue(out var item))
        {
            _queuedPaths.TryRemove(item.FilePath, out _);
            batch.Add(item);
        }

        return batch;
    }

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
