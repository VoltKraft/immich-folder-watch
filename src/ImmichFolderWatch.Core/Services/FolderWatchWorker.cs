using System.Collections.Concurrent;
using System.Globalization;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Core.Services;

public sealed class FolderWatchWorker : BackgroundService
{
    private static readonly TimeSpan DebounceDelay = TimeSpan.FromMilliseconds(750);

    private readonly AppConfig _config;

    private readonly IFileReadinessChecker _fileReadinessChecker;

    private readonly IUploadBatchQueue _uploadBatchQueue;

    private readonly IImmichAssetClient _immichAssetClient;

    private readonly SyncStatusProvider _syncStatusProvider;

    private readonly ILogger<FolderWatchWorker> _logger;

    private readonly ConcurrentDictionary<string, PendingFile> _debouncedFiles = new(StringComparer.OrdinalIgnoreCase);

    private readonly List<FileSystemWatcher> _watchers = new();

    private readonly TimeSpan _batchInterval;

    private readonly TimeSpan _fileReadyTimeout;

    public FolderWatchWorker(
        AppConfig config,
        IFileReadinessChecker fileReadinessChecker,
        IUploadBatchQueue uploadBatchQueue,
        IImmichAssetClient immichAssetClient,
        SyncStatusProvider syncStatusProvider,
        ILogger<FolderWatchWorker> logger)
    {
        _config = config;
        _fileReadinessChecker = fileReadinessChecker;
        _uploadBatchQueue = uploadBatchQueue;
        _immichAssetClient = immichAssetClient;
        _syncStatusProvider = syncStatusProvider;
        _logger = logger;
        _batchInterval = TimeSpan.FromSeconds(config.Watch.BatchIntervalSeconds);
        _fileReadyTimeout = TimeSpan.FromSeconds(config.Watch.FileReadyTimeoutSeconds);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        RegisterWatchers();

        _logger.LogInformation("Folder watcher started with {SourceCount} source(s).", _watchers.Count);

        using var loopTimer = new PeriodicTimer(TimeSpan.FromSeconds(1));
        var lastFlush = DateTimeOffset.UtcNow;

        try
        {
            while (await loopTimer.WaitForNextTickAsync(stoppingToken))
            {
                await PromoteDebouncedFilesAsync(stoppingToken);
                _syncStatusProvider.ReportPendingCount(_uploadBatchQueue.Count);

                var batchDue = DateTimeOffset.UtcNow - lastFlush >= _batchInterval;
                if (_uploadBatchQueue.Count >= _config.Watch.MaxBatchSize || batchDue)
                {
                    await FlushUploadsAsync(stoppingToken);
                    lastFlush = DateTimeOffset.UtcNow;
                    _syncStatusProvider.ReportPendingCount(_uploadBatchQueue.Count);
                }
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            _logger.LogInformation("Folder watch worker received shutdown signal.");
        }
        finally
        {
            _logger.LogInformation("Flushing pending uploads before shutdown.");
            await PromoteDebouncedFilesAsync(CancellationToken.None);
            await FlushUploadsAsync(CancellationToken.None);
            _syncStatusProvider.ReportPendingCount(_uploadBatchQueue.Count);
            DisposeWatchers();
        }
    }

    private void RegisterWatchers()
    {
        foreach (var source in _config.Watch.Sources)
        {
            if (!Directory.Exists(source.Path))
            {
                _logger.LogWarning("Watch source directory does not exist and was skipped: {Path}", source.Path);
                continue;
            }

            var sourceFilter = new WatchSourceFileFilter(source);
            var watcher = new FileSystemWatcher(source.Path)
            {
                IncludeSubdirectories = source.IncludeSubdirectories,
                NotifyFilter = NotifyFilters.FileName
                    | NotifyFilters.CreationTime
                    | NotifyFilters.LastWrite
                    | NotifyFilters.Size,
                EnableRaisingEvents = true,
            };

            watcher.Created += (_, e) => OnFileEvent(e.FullPath, source.AlbumName, sourceFilter);
            watcher.Changed += (_, e) => OnFileEvent(e.FullPath, source.AlbumName, sourceFilter);
            watcher.Renamed += (_, e) => OnFileEvent(e.FullPath, source.AlbumName, sourceFilter);
            watcher.Error += (_, e) => _logger.LogError(e.GetException(), "File watcher error for source {Path}", source.Path);

            _watchers.Add(watcher);

            _logger.LogInformation(
                "Watching source {Path} (Album: {AlbumName}, IncludeSubdirectories: {IncludeSubdirectories}).",
                source.Path,
                source.AlbumName,
                source.IncludeSubdirectories);
        }

        if (_watchers.Count == 0)
        {
            throw new InvalidOperationException("No valid watch source directories are available.");
        }
    }

    private void OnFileEvent(string filePath, string albumName, WatchSourceFileFilter sourceFilter)
    {
        if (!sourceFilter.IsMatch(filePath))
        {
            return;
        }

        var normalizedPath = NormalizePath(filePath);
        var timestamp = DateTimeOffset.UtcNow;

        _debouncedFiles.AddOrUpdate(
            normalizedPath,
            _ => new PendingFile(albumName, timestamp),
            (_, _) => new PendingFile(albumName, timestamp));

        _logger.LogDebug("File event captured for {FilePath}; waiting for debounce.", normalizedPath);
    }

    private async Task PromoteDebouncedFilesAsync(CancellationToken cancellationToken)
    {
        var now = DateTimeOffset.UtcNow;
        var maturedPaths = _debouncedFiles
            .Where(pair => now - pair.Value.LastEventUtc >= DebounceDelay)
            .Select(pair => pair.Key)
            .ToList();

        foreach (var path in maturedPaths)
        {
            if (!_debouncedFiles.TryRemove(path, out var pendingFile))
            {
                continue;
            }

            if (!File.Exists(path))
            {
                _logger.LogDebug("Skipping missing file {FilePath}.", path);
                continue;
            }

            var isReady = await _fileReadinessChecker.WaitUntilReadyAsync(path, _fileReadyTimeout, cancellationToken);
            if (!isReady)
            {
                _logger.LogWarning(
                    "File was not ready before timeout ({TimeoutSeconds}s): {FilePath}",
                    _config.Watch.FileReadyTimeoutSeconds,
                    path);
                continue;
            }

            var queued = _uploadBatchQueue.TryEnqueue(new UploadAssetRequest(path, pendingFile.AlbumName));
            if (queued)
            {
                _logger.LogInformation("Queued file {FilePath} for upload (Album: {AlbumName}).", path, pendingFile.AlbumName);
            }
            else
            {
                _logger.LogDebug("Duplicate queue entry ignored for file {FilePath}.", path);
            }
        }
    }

    private async Task FlushUploadsAsync(CancellationToken cancellationToken)
    {
        while (true)
        {
            var batch = _uploadBatchQueue.DequeueBatch(_config.Watch.MaxBatchSize);
            if (batch.Count == 0)
            {
                return;
            }

            _logger.LogInformation("Uploading batch with {Count} file(s).", batch.Count);
            _syncStatusProvider.ReportBatchStarted(batch.Count);

            foreach (var request in batch)
            {
                cancellationToken.ThrowIfCancellationRequested();

                if (!File.Exists(request.FilePath))
                {
                    _logger.LogWarning("Skipping upload because file no longer exists: {FilePath}", request.FilePath);
                    continue;
                }

                _syncStatusProvider.ReportUploadStarted(request.FilePath);
                var result = await _immichAssetClient.UploadAssetAsync(request, cancellationToken);
                if (result.IsSuccess)
                {
                    _logger.LogInformation(
                        "Upload succeeded for {FilePath} (Album: {AlbumName}, AssetId: {AssetId}).",
                        request.FilePath,
                        request.AlbumName,
                        result.AssetId ?? "n/a");
                    _syncStatusProvider.ReportUploadCompleted(request.FilePath);
                    _syncStatusProvider.ReportServerReachable(true);
                }
                else
                {
                    _logger.LogError(
                        "Upload failed for {FilePath} (Album: {AlbumName}). StatusCode={StatusCode}; Error={Error}",
                        request.FilePath,
                        request.AlbumName,
                        result.StatusCode.HasValue
                            ? ((int)result.StatusCode.Value).ToString(CultureInfo.InvariantCulture)
                            : "n/a",
                        result.ErrorMessage ?? "unknown error");
                    _syncStatusProvider.ReportUploadFailed(request.FilePath, result.ErrorMessage);
                }
            }

            _syncStatusProvider.ReportBatchCompleted();
        }
    }

    private static string NormalizePath(string path)
    {
        try
        {
            return Path.GetFullPath(path);
        }
        catch (Exception)
        {
            return path;
        }
    }

    private void DisposeWatchers()
    {
        foreach (var watcher in _watchers)
        {
            watcher.Dispose();
        }

        _watchers.Clear();
    }

    private sealed record PendingFile(string AlbumName, DateTimeOffset LastEventUtc);
}
