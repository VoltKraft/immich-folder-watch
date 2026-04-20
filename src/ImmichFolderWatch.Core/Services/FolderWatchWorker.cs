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

    private static readonly TimeSpan AlbumPullInterval = TimeSpan.FromSeconds(60);

    private readonly AppConfig _config;

    private readonly IFileReadinessChecker _fileReadinessChecker;

    private readonly IUploadBatchQueue _uploadBatchQueue;

    private readonly IImmichAssetClient _immichAssetClient;

    private readonly SyncStatusProvider _syncStatusProvider;

    private readonly ILogger<FolderWatchWorker> _logger;

    private readonly ConcurrentDictionary<string, PendingFile> _debouncedFiles = new(StringComparer.OrdinalIgnoreCase);

    private readonly List<FileSystemWatcher> _watchers = new();

    private readonly List<SyncSourceContext> _syncSources = new();

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

        SeedExistingFiles(stoppingToken);
        await InitialAlbumPullAsync(stoppingToken);

        using var loopTimer = new PeriodicTimer(TimeSpan.FromSeconds(1));
        var lastFlush = DateTimeOffset.UtcNow;
        var lastAlbumPull = DateTimeOffset.UtcNow;

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

                if (DateTimeOffset.UtcNow - lastAlbumPull >= AlbumPullInterval)
                {
                    await PullAlbumsForSyncSourcesAsync(stoppingToken);
                    lastAlbumPull = DateTimeOffset.UtcNow;
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
            var syncMode = WatchSourceSyncModes.Normalize(source.SyncMode);
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

            if (string.Equals(syncMode, WatchSourceSyncModes.Sync, StringComparison.Ordinal))
            {
                watcher.Deleted += (_, e) => _ = HandleLocalDeletionAsync(e.FullPath, source.AlbumName, sourceFilter);
                watcher.Renamed += (_, e) => _ = HandleLocalDeletionAsync(e.OldFullPath, source.AlbumName, sourceFilter);
            }

            watcher.Error += (_, e) => _logger.LogError(e.GetException(), "File watcher error for source {Path}", source.Path);

            _watchers.Add(watcher);

            if (!string.Equals(syncMode, WatchSourceSyncModes.UploadNew, StringComparison.Ordinal))
            {
                _syncSources.Add(new SyncSourceContext(source, sourceFilter, syncMode));
            }

            _logger.LogInformation(
                "Watching source {Path} (Album: {AlbumName}, IncludeSubdirectories: {IncludeSubdirectories}, SyncMode: {SyncMode}).",
                source.Path,
                source.AlbumName,
                source.IncludeSubdirectories,
                syncMode);
        }

        if (_watchers.Count == 0)
        {
            throw new InvalidOperationException("No valid watch source directories are available.");
        }
    }

    private void SeedExistingFiles(CancellationToken cancellationToken)
    {
        foreach (var context in _syncSources)
        {
            cancellationToken.ThrowIfCancellationRequested();

            int queuedCount = 0;
            try
            {
                var searchOption = context.Source.IncludeSubdirectories
                    ? SearchOption.AllDirectories
                    : SearchOption.TopDirectoryOnly;

                foreach (var filePath in Directory.EnumerateFiles(context.Source.Path, "*", searchOption))
                {
                    if (!context.Filter.IsMatch(filePath))
                    {
                        continue;
                    }

                    var normalized = NormalizePath(filePath);
                    if (_uploadBatchQueue.TryEnqueue(new UploadAssetRequest(normalized, context.Source.AlbumName)))
                    {
                        queuedCount++;
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Initial scan failed for source {Path}.", context.Source.Path);
                continue;
            }

            _logger.LogInformation(
                "Initial scan for {SyncMode} queued {Count} existing file(s) from {Path}.",
                context.SyncMode,
                queuedCount,
                context.Source.Path);
        }

        _syncStatusProvider.ReportPendingCount(_uploadBatchQueue.Count);
    }

    private async Task InitialAlbumPullAsync(CancellationToken cancellationToken)
    {
        foreach (var context in _syncSources)
        {
            if (!string.Equals(context.SyncMode, WatchSourceSyncModes.Sync, StringComparison.Ordinal))
            {
                continue;
            }

            await PullAlbumForSourceAsync(context, cancellationToken);
        }
    }

    private async Task PullAlbumsForSyncSourcesAsync(CancellationToken cancellationToken)
    {
        foreach (var context in _syncSources)
        {
            if (!string.Equals(context.SyncMode, WatchSourceSyncModes.Sync, StringComparison.Ordinal))
            {
                continue;
            }

            await PullAlbumForSourceAsync(context, cancellationToken);
        }
    }

    private async Task PullAlbumForSourceAsync(SyncSourceContext context, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();

        if (string.IsNullOrWhiteSpace(context.Source.AlbumName))
        {
            return;
        }

        AlbumAssetsResult result;
        try
        {
            result = await _immichAssetClient.GetAlbumAssetsAsync(context.Source.AlbumName, cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Listing album '{AlbumName}' for sync pull failed.", context.Source.AlbumName);
            return;
        }

        if (result.AlbumMissing)
        {
            _logger.LogDebug("Sync pull skipped; album '{AlbumName}' does not exist yet.", context.Source.AlbumName);
            return;
        }

        if (!result.IsSuccess)
        {
            _logger.LogWarning(
                "Sync pull failed for album '{AlbumName}': {Error}",
                context.Source.AlbumName,
                result.ErrorMessage ?? "unknown");
            return;
        }

        var localFileNames = EnumerateLocalFileNames(context);
        var downloadedCount = 0;

        foreach (var asset in result.Assets)
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (string.IsNullOrWhiteSpace(asset.OriginalFileName))
            {
                continue;
            }

            if (localFileNames.Contains(asset.OriginalFileName))
            {
                continue;
            }

            var destinationPath = Path.Combine(context.Source.Path, asset.OriginalFileName);
            if (!context.Filter.IsMatch(destinationPath))
            {
                continue;
            }

            if (File.Exists(destinationPath))
            {
                continue;
            }

            var download = await _immichAssetClient.DownloadAssetAsync(asset.Id, destinationPath, cancellationToken);
            if (download.IsSuccess)
            {
                downloadedCount++;
                _logger.LogInformation(
                    "Downloaded asset {AssetId} to {FilePath} from album '{AlbumName}'.",
                    asset.Id,
                    destinationPath,
                    context.Source.AlbumName);
            }
            else
            {
                _logger.LogWarning(
                    "Downloading asset {AssetId} failed: {Error}",
                    asset.Id,
                    download.ErrorMessage ?? "unknown");
            }
        }

        if (downloadedCount > 0)
        {
            _logger.LogInformation(
                "Sync pull finished for album '{AlbumName}' ({Count} new file(s) downloaded).",
                context.Source.AlbumName,
                downloadedCount);
        }
    }

    private static HashSet<string> EnumerateLocalFileNames(SyncSourceContext context)
    {
        var set = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        try
        {
            var searchOption = context.Source.IncludeSubdirectories
                ? SearchOption.AllDirectories
                : SearchOption.TopDirectoryOnly;

            foreach (var filePath in Directory.EnumerateFiles(context.Source.Path, "*", searchOption))
            {
                set.Add(Path.GetFileName(filePath));
            }
        }
        catch (Exception)
        {
        }

        return set;
    }

    private Task HandleLocalDeletionAsync(string filePath, string albumName, WatchSourceFileFilter sourceFilter)
    {
        if (string.IsNullOrWhiteSpace(albumName) || !sourceFilter.IsMatch(filePath))
        {
            return Task.CompletedTask;
        }

        var fileName = Path.GetFileName(filePath);
        if (string.IsNullOrWhiteSpace(fileName))
        {
            return Task.CompletedTask;
        }

        _logger.LogInformation(
            "Local deletion of {FileName} detected in sync source for album '{AlbumName}'. Remote deletion is not yet implemented and must be performed manually.",
            fileName,
            albumName);

        return Task.CompletedTask;
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

    private sealed record SyncSourceContext(WatchSourceSettings Source, WatchSourceFileFilter Filter, string SyncMode);
}
