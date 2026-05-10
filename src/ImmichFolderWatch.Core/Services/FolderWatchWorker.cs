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

    private static readonly TimeSpan AlbumPullInterval = TimeSpan.FromSeconds(10);

    // Periodic polling sweep alongside FileSystemWatcher. FSW is reliable
    // on native NTFS / ext4 / btrfs, but inotify on FUSE mounts (notably
    // the Flatpak xdg-document-portal at /run/user/$UID/doc/<token>/...)
    // does not propagate file changes that originate outside the mount.
    // The sweep diff-scans the source trees against a known-paths
    // baseline: new files replay into OnFileEvent; missing files
    // replay into HandleDeleteInSyncAsync (sync mode only — non-sync
    // modes have no delete propagation anyway). On platforms where
    // FSW already fired the events, OnFileEvent debounces against
    // _debouncedFiles and HandleDeleteInSyncAsync no-ops on the
    // already-removed _pathToAssetId entry, so the sweep is cheap.
    private static readonly TimeSpan PollingSweepInterval = TimeSpan.FromSeconds(5);

    private readonly Dictionary<string, HashSet<string>> _pollingBaseline =
        new(StringComparer.OrdinalIgnoreCase);

    private DateTimeOffset _lastPollingSweep = DateTimeOffset.MinValue;

    private readonly AppConfig _config;

    private readonly IFileReadinessChecker _fileReadinessChecker;

    private readonly IUploadBatchQueue _uploadBatchQueue;

    private readonly IImmichAssetClient _immichAssetClient;

    private readonly IImmichRealtimeClient? _immichRealtimeClient;

    private readonly SyncStatusProvider _syncStatusProvider;

    private readonly ILogger<FolderWatchWorker> _logger;

    private volatile int _pullRequested;

    private readonly ConcurrentDictionary<string, PendingFile> _debouncedFiles = new(StringComparer.OrdinalIgnoreCase);

    private readonly ConcurrentDictionary<string, string> _pathToAssetId = new(StringComparer.OrdinalIgnoreCase);

    private readonly ConcurrentDictionary<string, string> _albumIdToDirName = new(StringComparer.Ordinal);

    private readonly List<FileSystemWatcher> _watchers = new();

    private readonly List<WatchSourceContext> _sources = new();

    private readonly TimeSpan _batchInterval;

    private readonly TimeSpan _fileReadyTimeout;

    public FolderWatchWorker(
        AppConfig config,
        IFileReadinessChecker fileReadinessChecker,
        IUploadBatchQueue uploadBatchQueue,
        IImmichAssetClient immichAssetClient,
        SyncStatusProvider syncStatusProvider,
        ILogger<FolderWatchWorker> logger,
        IImmichRealtimeClient? immichRealtimeClient = null)
    {
        _config = config;
        _fileReadinessChecker = fileReadinessChecker;
        _uploadBatchQueue = uploadBatchQueue;
        _immichAssetClient = immichAssetClient;
        _immichRealtimeClient = immichRealtimeClient;
        _syncStatusProvider = syncStatusProvider;
        _logger = logger;
        _batchInterval = TimeSpan.FromSeconds(config.Watch.BatchIntervalSeconds);
        _fileReadyTimeout = TimeSpan.FromSeconds(config.Watch.FileReadyTimeoutSeconds);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        RegisterWatchers();

        _logger.LogInformation("Folder watcher started with {SourceCount} source(s).", _watchers.Count);

        await BuildInitialAssetMapAsync(stoppingToken);
        SeedExistingFiles(stoppingToken);
        await PullFromImmichAsync(stoppingToken);

        if (_immichRealtimeClient is not null)
        {
            _immichRealtimeClient.RemoteChangeDetected += OnRemoteChangeDetected;
            _ = Task.Run(() => _immichRealtimeClient.StartAsync(stoppingToken), stoppingToken);
        }

        using var loopTimer = new PeriodicTimer(TimeSpan.FromSeconds(1));
        var lastFlush = DateTimeOffset.UtcNow;
        var lastAlbumPull = DateTimeOffset.UtcNow;

        try
        {
            while (await loopTimer.WaitForNextTickAsync(stoppingToken))
            {
                if (DateTimeOffset.UtcNow - _lastPollingSweep >= PollingSweepInterval)
                {
                    PollDirectoriesForChanges();
                    _lastPollingSweep = DateTimeOffset.UtcNow;
                }

                await PromoteDebouncedFilesAsync(stoppingToken);
                _syncStatusProvider.ReportPendingCount(_uploadBatchQueue.Count);

                var batchDue = DateTimeOffset.UtcNow - lastFlush >= _batchInterval;
                if (_uploadBatchQueue.Count >= _config.Watch.MaxBatchSize || batchDue)
                {
                    await FlushUploadsAsync(stoppingToken);
                    lastFlush = DateTimeOffset.UtcNow;
                    _syncStatusProvider.ReportPendingCount(_uploadBatchQueue.Count);
                }

                var pullRequested = Interlocked.Exchange(ref _pullRequested, 0) == 1;
                if (pullRequested || DateTimeOffset.UtcNow - lastAlbumPull >= AlbumPullInterval)
                {
                    await PullFromImmichAsync(stoppingToken);
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
            if (_immichRealtimeClient is not null)
            {
                _immichRealtimeClient.RemoteChangeDetected -= OnRemoteChangeDetected;
                try
                {
                    await _immichRealtimeClient.StopAsync(CancellationToken.None);
                }
                catch (Exception ex)
                {
                    _logger.LogDebug(ex, "Realtime client stop threw during shutdown.");
                }
            }

            _logger.LogInformation("Flushing pending uploads before shutdown.");
            await PromoteDebouncedFilesAsync(CancellationToken.None);
            await FlushUploadsAsync(CancellationToken.None);
            _syncStatusProvider.ReportPendingCount(_uploadBatchQueue.Count);
            DisposeWatchers();
        }
    }

    private void OnRemoteChangeDetected(object? sender, EventArgs e)
    {
        Interlocked.Exchange(ref _pullRequested, 1);
    }

    private void RegisterWatchers()
    {
        var inotifyLimit = InotifyLimits.GetMaxUserWatches();
        var inotifyConsumed = 0L;
        var inotifyWarned = false;

        foreach (var source in _config.Watch.Sources)
        {
            if (!Directory.Exists(source.Path))
            {
                _logger.LogWarning("Watch source directory does not exist and was skipped: {Path}", source.Path);
                continue;
            }

            if (inotifyLimit.HasValue)
            {
                var estimated = InotifyLimits.CountWatchedDirectories(source.Path, source.IncludeSubdirectories);
                var projected = inotifyConsumed + estimated;
                if (projected > inotifyLimit.Value * InotifyLimits.RefuseFraction)
                {
                    _logger.LogError(
                        "Skipping source {Path}: registering ~{Estimated} inotify watches would push the user total to {Projected}, exceeding 95% of fs.inotify.max_user_watches={Limit}. Increase the limit (e.g. sysctl fs.inotify.max_user_watches=524288) or remove sources.",
                        source.Path,
                        estimated,
                        projected,
                        inotifyLimit.Value);
                    continue;
                }

                if (!inotifyWarned && projected > inotifyLimit.Value * InotifyLimits.WarnFraction)
                {
                    _logger.LogWarning(
                        "Configured watch tree consumes {Projected} of {Limit} inotify watches (>50% of fs.inotify.max_user_watches). Increase the limit if you plan to add more sources.",
                        projected,
                        inotifyLimit.Value);
                    inotifyWarned = true;
                }

                inotifyConsumed = projected;
            }

            var syncMode = WatchSourceSyncModes.Normalize(source.SyncMode);
            var isSyncMode = string.Equals(syncMode, WatchSourceSyncModes.Sync, StringComparison.Ordinal);
            var useSubdirsAsAlbums = isSyncMode && string.IsNullOrWhiteSpace(source.AlbumName);
            var useFlatAlbum = isSyncMode && !string.IsNullOrWhiteSpace(source.AlbumName);
            var effectiveIncludeSubdirectories = useSubdirsAsAlbums
                || (!isSyncMode && source.IncludeSubdirectories);

            var filter = new WatchSourceFileFilter(source);
            var normalizedRoot = NormalizeDirectory(source.Path);
            var context = new WatchSourceContext(
                source,
                syncMode,
                filter,
                normalizedRoot,
                useSubdirsAsAlbums,
                useFlatAlbum,
                effectiveIncludeSubdirectories);

            var watcher = new FileSystemWatcher(source.Path)
            {
                IncludeSubdirectories = effectiveIncludeSubdirectories,
                NotifyFilter = NotifyFilters.FileName
                    | NotifyFilters.CreationTime
                    | NotifyFilters.LastWrite
                    | NotifyFilters.Size,
                EnableRaisingEvents = true,
            };

            watcher.Created += (_, e) => OnFileEvent(context, e.FullPath);
            watcher.Changed += (_, e) => OnFileEvent(context, e.FullPath);

            if (isSyncMode)
            {
                watcher.Renamed += (_, e) => _ = HandleRenameInSyncAsync(context, e.OldFullPath, e.FullPath);
                watcher.Deleted += (_, e) => _ = HandleDeleteInSyncAsync(context, e.FullPath);
            }
            else
            {
                watcher.Renamed += (_, e) => OnFileEvent(context, e.FullPath);
            }

            watcher.Error += (_, e) => _logger.LogError(e.GetException(), "File watcher error for source {Path}", source.Path);

            _watchers.Add(watcher);
            _sources.Add(context);
            var baseline = SnapshotExistingFiles(context);
            _pollingBaseline[NormalizePath(source.Path)] = baseline;
            _logger.LogInformation(
                "Polling baseline established for {Path}: {Count} pre-existing file(s) snapshotted; sweep interval = {SweepSeconds}s.",
                source.Path,
                baseline.Count,
                (int)PollingSweepInterval.TotalSeconds);

            if (useSubdirsAsAlbums)
            {
                var dirWatcher = new FileSystemWatcher(source.Path)
                {
                    IncludeSubdirectories = false,
                    NotifyFilter = NotifyFilters.DirectoryName,
                    EnableRaisingEvents = true,
                };

                dirWatcher.Created += (_, e) => _ = HandleSubdirCreatedAsync(e.FullPath);
                dirWatcher.Deleted += (_, e) => _ = HandleSubdirDeletedAsync(e.FullPath);
                dirWatcher.Renamed += (_, e) => _ = HandleSubdirRenamedAsync(e.OldFullPath, e.FullPath);
                dirWatcher.Error += (_, e) => _logger.LogError(e.GetException(), "Directory watcher error for source {Path}", source.Path);

                _watchers.Add(dirWatcher);
            }

            _logger.LogInformation(
                "Watching source {Path} (Album: '{AlbumName}', SyncMode: {SyncMode}, IncludeSubdirectories: {IncludeSubdirectories}).",
                source.Path,
                source.AlbumName,
                syncMode,
                effectiveIncludeSubdirectories);
        }

        if (_watchers.Count == 0)
        {
            throw new InvalidOperationException("No valid watch source directories are available.");
        }
    }

    private async Task BuildInitialAssetMapAsync(CancellationToken cancellationToken)
    {
        foreach (var context in _sources)
        {
            if (!context.IsSyncMode)
            {
                continue;
            }

            cancellationToken.ThrowIfCancellationRequested();

            try
            {
                if (context.UseFlatAlbum)
                {
                    await MapFlatAlbumAsync(context, cancellationToken);
                }
                else if (context.UseSubdirsAsAlbums)
                {
                    await MapSubdirsAsAlbumsAsync(context, cancellationToken);
                }
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Initial asset map build failed for source {Path}.", context.Source.Path);
            }
        }
    }

    private async Task MapFlatAlbumAsync(WatchSourceContext context, CancellationToken cancellationToken)
    {
        var result = await _immichAssetClient.GetAlbumAssetsAsync(context.Source.AlbumName, cancellationToken);
        if (!result.IsSuccess)
        {
            if (!result.AlbumMissing)
            {
                _logger.LogWarning(
                    "Initial album map failed for '{AlbumName}': {Error}",
                    context.Source.AlbumName,
                    result.ErrorMessage ?? "unknown");
            }

            return;
        }

        foreach (var asset in result.Assets)
        {
            if (string.IsNullOrWhiteSpace(asset.OriginalFileName))
            {
                continue;
            }

            var filePath = Path.Combine(context.NormalizedRoot, asset.OriginalFileName);
            _pathToAssetId[NormalizePath(filePath)] = asset.Id;
        }
    }

    private async Task MapSubdirsAsAlbumsAsync(WatchSourceContext context, CancellationToken cancellationToken)
    {
        var unassigned = await _immichAssetClient.GetUnassignedAssetsAsync(cancellationToken);
        if (unassigned.IsSuccess)
        {
            foreach (var asset in unassigned.Assets)
            {
                if (string.IsNullOrWhiteSpace(asset.OriginalFileName))
                {
                    continue;
                }

                var filePath = Path.Combine(context.NormalizedRoot, asset.OriginalFileName);
                _pathToAssetId[NormalizePath(filePath)] = asset.Id;
            }
        }
        else
        {
            _logger.LogWarning(
                "Listing unassigned assets failed during initial map: {Error}",
                unassigned.ErrorMessage ?? "unknown");
        }

        var albums = await _immichAssetClient.ListAlbumsAsync(cancellationToken);
        if (!albums.IsSuccess)
        {
            _logger.LogWarning("Listing albums failed during initial map: {Error}", albums.ErrorMessage ?? "unknown");
            return;
        }

        foreach (var album in albums.Albums)
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (string.IsNullOrWhiteSpace(album.Name))
            {
                continue;
            }

            var sanitized = SanitizeDirectoryName(album.Name);
            if (string.IsNullOrWhiteSpace(sanitized))
            {
                continue;
            }

            _albumIdToDirName[album.Id] = sanitized;

            var albumDir = Path.Combine(context.NormalizedRoot, sanitized);
            var albumResult = await _immichAssetClient.GetAlbumAssetsAsync(album.Name, cancellationToken);
            if (!albumResult.IsSuccess)
            {
                continue;
            }

            foreach (var asset in albumResult.Assets)
            {
                if (string.IsNullOrWhiteSpace(asset.OriginalFileName))
                {
                    continue;
                }

                var filePath = Path.Combine(albumDir, asset.OriginalFileName);
                _pathToAssetId[NormalizePath(filePath)] = asset.Id;
            }
        }
    }

    private void SeedExistingFiles(CancellationToken cancellationToken)
    {
        foreach (var context in _sources)
        {
            if (string.Equals(context.SyncMode, WatchSourceSyncModes.UploadNew, StringComparison.Ordinal))
            {
                continue;
            }

            cancellationToken.ThrowIfCancellationRequested();

            var queuedCount = 0;
            try
            {
                var searchOption = context.EffectiveIncludeSubdirectories
                    ? SearchOption.AllDirectories
                    : SearchOption.TopDirectoryOnly;

                foreach (var filePath in Directory.EnumerateFiles(context.Source.Path, "*", searchOption))
                {
                    if (!context.Filter.IsMatch(filePath))
                    {
                        continue;
                    }

                    var normalized = NormalizePath(filePath);

                    if (context.IsSyncMode && _pathToAssetId.ContainsKey(normalized))
                    {
                        continue;
                    }

                    var albumName = GetEffectiveAlbum(context, normalized);
                    if (_uploadBatchQueue.TryEnqueue(new UploadAssetRequest(normalized, albumName)))
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

    private HashSet<string> SnapshotExistingFiles(WatchSourceContext context)
    {
        var set = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var searchOption = context.EffectiveIncludeSubdirectories
            ? SearchOption.AllDirectories
            : SearchOption.TopDirectoryOnly;
        try
        {
            foreach (var filePath in Directory.EnumerateFiles(context.Source.Path, "*", searchOption))
            {
                set.Add(NormalizePath(filePath));
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Polling baseline scan failed for {Path}", context.Source.Path);
        }
        return set;
    }

    private void PollDirectoriesForChanges()
    {
        foreach (var context in _sources)
        {
            var sourceKey = NormalizePath(context.Source.Path);
            if (!_pollingBaseline.TryGetValue(sourceKey, out var known))
            {
                continue;
            }

            var searchOption = context.EffectiveIncludeSubdirectories
                ? SearchOption.AllDirectories
                : SearchOption.TopDirectoryOnly;

            HashSet<string> seenThisSweep;
            try
            {
                seenThisSweep = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (var filePath in Directory.EnumerateFiles(context.Source.Path, "*", searchOption))
                {
                    var normalized = NormalizePath(filePath);
                    seenThisSweep.Add(normalized);

                    // HashSet.Add returns false if the path was already
                    // known — skip it. New paths fall through to
                    // OnFileEvent, which itself debounces against
                    // _debouncedFiles so a parallel FSW Created event
                    // does not double-enqueue.
                    if (!known.Add(normalized))
                    {
                        continue;
                    }
                    if (!context.Filter.IsMatch(normalized))
                    {
                        _logger.LogDebug("Polling sweep saw new file but filter rejected it: {Path}", normalized);
                        continue;
                    }
                    _logger.LogInformation("Polling sweep detected new file: {Path}", normalized);
                    OnFileEvent(context, normalized);
                }
            }
            catch (Exception ex)
            {
                _logger.LogDebug(ex, "Polling sweep failed for {Path}", context.Source.Path);
                continue;
            }

            // Detect deletions: paths in the known baseline that the
            // current scan didn't see. Mostly relevant on FUSE mounts
            // (Flatpak xdg-document-portal) where FSW.Deleted does not
            // fire; on native filesystems FSW already fired for these
            // and HandleDeleteInSyncAsync's _pathToAssetId.TryRemove
            // returns false, making the second call a cheap no-op.
            var disappeared = known.Where(p => !seenThisSweep.Contains(p)).ToList();
            foreach (var path in disappeared)
            {
                known.Remove(path);
                if (!context.Filter.IsMatch(path))
                {
                    continue;
                }
                _logger.LogInformation("Polling sweep detected removed file: {Path}", path);
                if (context.IsSyncMode)
                {
                    _ = HandleDeleteInSyncAsync(context, path);
                }
                else
                {
                    // Non-sync modes don't propagate deletes upward, but
                    // we still drop the asset-id mapping so a re-add of
                    // the same path later isn't mis-identified.
                    _debouncedFiles.TryRemove(path, out _);
                    _pathToAssetId.TryRemove(path, out _);
                }
            }
        }
    }

    private async Task PullFromImmichAsync(CancellationToken cancellationToken)
    {
        foreach (var context in _sources)
        {
            if (!context.IsSyncMode)
            {
                continue;
            }

            var remoteAssetIds = new HashSet<string>(StringComparer.Ordinal);
            var pullSucceeded = false;
            try
            {
                if (context.UseFlatAlbum)
                {
                    pullSucceeded = await PullFlatAlbumAsync(context, remoteAssetIds, cancellationToken);
                }
                else if (context.UseSubdirsAsAlbums)
                {
                    pullSucceeded = await PullSubdirsAsAlbumsAsync(context, remoteAssetIds, cancellationToken);
                }
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Sync pull failed for source {Path}.", context.Source.Path);
            }

            if (pullSucceeded)
            {
                PropagateRemoteDeletes(context, remoteAssetIds);
            }
        }
    }

    /// <summary>
    /// Removes local files whose <see cref="_pathToAssetId"/> mapping
    /// references an Immich asset id that the latest pull no longer
    /// reports — i.e. the user trashed the asset on Immich. Only runs
    /// when the pull as a whole succeeded; partial failures abort
    /// (we don't want to delete every local file because a transient
    /// API error returned an empty asset list).
    /// </summary>
    private void PropagateRemoteDeletes(WatchSourceContext context, HashSet<string> remoteAssetIds)
    {
        var rootPrefix = context.NormalizedRoot + Path.DirectorySeparatorChar;
        var sourceKey = NormalizePath(context.Source.Path);
        _pollingBaseline.TryGetValue(sourceKey, out var baseline);

        var stale = _pathToAssetId
            .Where(entry =>
                entry.Key.StartsWith(rootPrefix, StringComparison.OrdinalIgnoreCase)
                && !remoteAssetIds.Contains(entry.Value))
            .ToList();

        foreach (var entry in stale)
        {
            if (!_pathToAssetId.TryRemove(entry.Key, out _))
            {
                continue;
            }

            // Drop from polling baseline so the next sweep doesn't
            // re-fire HandleDeleteInSyncAsync against an asset id we
            // already cleaned up.
            baseline?.Remove(entry.Key);
            _debouncedFiles.TryRemove(entry.Key, out _);

            try
            {
                if (File.Exists(entry.Key))
                {
                    File.Delete(entry.Key);
                    _logger.LogInformation(
                        "Removed local file after remote delete (asset {AssetId} no longer on Immich): {Path}",
                        entry.Value,
                        entry.Key);
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(
                    ex,
                    "Failed to remove local file after remote delete: {Path}",
                    entry.Key);
            }
        }
    }

    private async Task<bool> PullFlatAlbumAsync(
        WatchSourceContext context,
        HashSet<string> remoteAssetIds,
        CancellationToken cancellationToken)
    {
        var result = await _immichAssetClient.GetAlbumAssetsAsync(context.Source.AlbumName, cancellationToken);
        if (result.AlbumMissing)
        {
            // We can't tell "album never existed" from "album was just
            // deleted by the user". Skip delete propagation either way
            // — a fresh upload re-creates the album, and the next pull
            // sees the new state.
            _logger.LogDebug("Sync pull skipped; album '{AlbumName}' does not exist yet.", context.Source.AlbumName);
            return false;
        }

        if (!result.IsSuccess)
        {
            _logger.LogWarning(
                "Sync pull failed for album '{AlbumName}': {Error}",
                context.Source.AlbumName,
                result.ErrorMessage ?? "unknown");
            return false;
        }

        foreach (var asset in result.Assets)
        {
            if (!string.IsNullOrWhiteSpace(asset.Id))
            {
                remoteAssetIds.Add(asset.Id);
            }
        }

        await DownloadAssetsAsync(context, context.NormalizedRoot, result.Assets, cancellationToken);
        return true;
    }

    private async Task<bool> PullSubdirsAsAlbumsAsync(
        WatchSourceContext context,
        HashSet<string> remoteAssetIds,
        CancellationToken cancellationToken)
    {
        var allOk = true;

        var unassigned = await _immichAssetClient.GetUnassignedAssetsAsync(cancellationToken);
        if (unassigned.IsSuccess)
        {
            foreach (var asset in unassigned.Assets)
            {
                if (!string.IsNullOrWhiteSpace(asset.Id))
                {
                    remoteAssetIds.Add(asset.Id);
                }
            }
            await DownloadAssetsAsync(context, context.NormalizedRoot, unassigned.Assets, cancellationToken);
        }
        else
        {
            _logger.LogWarning(
                "Listing unassigned assets failed during sync pull: {Error}",
                unassigned.ErrorMessage ?? "unknown");
            allOk = false;
        }

        var albums = await _immichAssetClient.ListAlbumsAsync(cancellationToken);
        if (!albums.IsSuccess)
        {
            _logger.LogWarning("Listing albums failed during sync pull: {Error}", albums.ErrorMessage ?? "unknown");
            return false;
        }

        foreach (var album in albums.Albums)
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (string.IsNullOrWhiteSpace(album.Name))
            {
                continue;
            }

            var sanitized = SanitizeDirectoryName(album.Name);
            if (string.IsNullOrWhiteSpace(sanitized))
            {
                continue;
            }

            if (_albumIdToDirName.TryGetValue(album.Id, out var previousDirName)
                && !string.Equals(previousDirName, sanitized, StringComparison.Ordinal))
            {
                var previousDir = Path.Combine(context.NormalizedRoot, previousDirName);
                var targetDir = Path.Combine(context.NormalizedRoot, sanitized);
                TryRenameLocalSubdir(previousDir, targetDir, previousDirName, sanitized);
            }

            _albumIdToDirName[album.Id] = sanitized;

            var albumDir = Path.Combine(context.NormalizedRoot, sanitized);

            var albumResult = await _immichAssetClient.GetAlbumAssetsAsync(album.Name, cancellationToken);
            if (!albumResult.IsSuccess)
            {
                if (!albumResult.AlbumMissing)
                {
                    _logger.LogWarning(
                        "Sync pull failed for album '{AlbumName}': {Error}",
                        album.Name,
                        albumResult.ErrorMessage ?? "unknown");
                    allOk = false;
                }

                continue;
            }

            foreach (var asset in albumResult.Assets)
            {
                if (!string.IsNullOrWhiteSpace(asset.Id))
                {
                    remoteAssetIds.Add(asset.Id);
                }
            }

            await DownloadAssetsAsync(context, albumDir, albumResult.Assets, cancellationToken);
        }

        return allOk;
    }

    private async Task DownloadAssetsAsync(
        WatchSourceContext context,
        string targetDirectory,
        IReadOnlyList<AlbumAssetSummary> assets,
        CancellationToken cancellationToken)
    {
        var pending = new List<(AlbumAssetSummary Asset, string DestinationPath)>();

        foreach (var asset in assets)
        {
            cancellationToken.ThrowIfCancellationRequested();

            if (string.IsNullOrWhiteSpace(asset.OriginalFileName))
            {
                continue;
            }

            var destinationPath = Path.Combine(targetDirectory, asset.OriginalFileName);
            var normalized = NormalizePath(destinationPath);
            _pathToAssetId[normalized] = asset.Id;

            if (!context.Filter.IsMatch(destinationPath))
            {
                continue;
            }

            if (File.Exists(destinationPath))
            {
                continue;
            }

            pending.Add((asset, destinationPath));
        }

        if (pending.Count == 0)
        {
            return;
        }

        _syncStatusProvider.ReportPullStarted(pending.Count);
        try
        {
            var downloadedCount = 0;
            foreach (var (asset, destinationPath) in pending)
            {
                cancellationToken.ThrowIfCancellationRequested();

                _syncStatusProvider.ReportDownloadStarted(destinationPath);
                var download = await _immichAssetClient.DownloadAssetAsync(asset.Id, destinationPath, cancellationToken);
                if (download.IsSuccess)
                {
                    downloadedCount++;
                    _syncStatusProvider.ReportDownloadCompleted(destinationPath);
                    _logger.LogInformation(
                        "Downloaded asset {AssetId} to {FilePath}.",
                        asset.Id,
                        destinationPath);
                }
                else
                {
                    _syncStatusProvider.ReportDownloadFailed(destinationPath, download.ErrorMessage);
                    _logger.LogWarning(
                        "Downloading asset {AssetId} failed: {Error}",
                        asset.Id,
                        download.ErrorMessage ?? "unknown");
                }
            }

            if (downloadedCount > 0)
            {
                _logger.LogInformation(
                    "Sync pull downloaded {Count} new file(s) into {Directory}.",
                    downloadedCount,
                    targetDirectory);
            }
        }
        finally
        {
            _syncStatusProvider.ReportPullCompleted();
        }
    }

    private static string GetEffectiveAlbum(WatchSourceContext context, string normalizedFilePath)
    {
        if (!context.UseSubdirsAsAlbums)
        {
            return context.Source.AlbumName;
        }

        var relative = Path.GetRelativePath(context.NormalizedRoot, normalizedFilePath);
        if (string.IsNullOrWhiteSpace(relative) || relative.StartsWith("..", StringComparison.Ordinal))
        {
            return string.Empty;
        }

        var separatorIndex = relative.IndexOfAny(new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar });
        return separatorIndex < 0 ? string.Empty : relative[..separatorIndex];
    }

    private void OnFileEvent(WatchSourceContext context, string filePath)
    {
        if (!context.Filter.IsMatch(filePath))
        {
            return;
        }

        var normalizedPath = NormalizePath(filePath);
        var albumName = GetEffectiveAlbum(context, normalizedPath);
        var timestamp = DateTimeOffset.UtcNow;

        _debouncedFiles.AddOrUpdate(
            normalizedPath,
            _ => new PendingFile(albumName, timestamp),
            (_, _) => new PendingFile(albumName, timestamp));

        _logger.LogDebug("File event captured for {FilePath}; waiting for debounce.", normalizedPath);
    }

    private async Task HandleRenameInSyncAsync(WatchSourceContext context, string oldFullPath, string newFullPath)
    {
        try
        {
            var oldNormalized = NormalizePath(oldFullPath);
            var newNormalized = NormalizePath(newFullPath);
            var oldAlbum = GetEffectiveAlbum(context, oldNormalized);
            var newAlbum = GetEffectiveAlbum(context, newNormalized);
            var hadAssetId = _pathToAssetId.TryRemove(oldNormalized, out var assetId);
            var newMatches = context.Filter.IsMatch(newFullPath);

            _debouncedFiles.TryRemove(oldNormalized, out _);

            if (hadAssetId && newMatches)
            {
                if (!string.Equals(oldAlbum, newAlbum, StringComparison.Ordinal))
                {
                    var ids = new[] { assetId! };
                    if (!string.IsNullOrWhiteSpace(newAlbum))
                    {
                        var add = await _immichAssetClient.AddAssetsToAlbumAsync(newAlbum, ids, CancellationToken.None);
                        if (!add.IsSuccess)
                        {
                            _logger.LogWarning(
                                "Failed to add asset {AssetId} to album '{AlbumName}': {Error}",
                                assetId,
                                newAlbum,
                                add.ErrorMessage ?? "unknown");
                        }
                    }

                    if (!string.IsNullOrWhiteSpace(oldAlbum))
                    {
                        var remove = await _immichAssetClient.RemoveAssetsFromAlbumAsync(oldAlbum, ids, CancellationToken.None);
                        if (!remove.IsSuccess)
                        {
                            _logger.LogWarning(
                                "Failed to remove asset {AssetId} from album '{AlbumName}': {Error}",
                                assetId,
                                oldAlbum,
                                remove.ErrorMessage ?? "unknown");
                        }
                    }

                    _logger.LogInformation(
                        "Asset {AssetId} moved from album '{OldAlbum}' to '{NewAlbum}' ({OldPath} -> {NewPath}).",
                        assetId,
                        string.IsNullOrWhiteSpace(oldAlbum) ? "(unassigned)" : oldAlbum,
                        string.IsNullOrWhiteSpace(newAlbum) ? "(unassigned)" : newAlbum,
                        oldNormalized,
                        newNormalized);
                }

                _pathToAssetId[newNormalized] = assetId!;
                return;
            }

            if (hadAssetId)
            {
                await TrashAssetAsync(assetId!, oldNormalized);
                return;
            }

            if (newMatches)
            {
                OnFileEvent(context, newFullPath);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to handle rename {OldPath} -> {NewPath}.", oldFullPath, newFullPath);
        }
    }

    private async Task HandleDeleteInSyncAsync(WatchSourceContext context, string oldFullPath)
    {
        try
        {
            var normalized = NormalizePath(oldFullPath);
            _debouncedFiles.TryRemove(normalized, out _);

            if (!_pathToAssetId.TryRemove(normalized, out var assetId))
            {
                _logger.LogDebug("Local deletion without known asset id for {FilePath}.", normalized);
                return;
            }

            await TrashAssetAsync(assetId, normalized);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to handle deletion of {FilePath}.", oldFullPath);
        }
    }

    private async Task HandleSubdirCreatedAsync(string fullPath)
    {
        try
        {
            var dirName = Path.GetFileName(NormalizeDirectory(fullPath));
            if (string.IsNullOrWhiteSpace(dirName))
            {
                return;
            }

            var result = await _immichAssetClient.EnsureAlbumAsync(dirName, CancellationToken.None);
            if (result.IsSuccess)
            {
                if (!string.IsNullOrWhiteSpace(result.AlbumId))
                {
                    _albumIdToDirName[result.AlbumId!] = dirName;
                }

                _logger.LogInformation("Ensured album '{AlbumName}' after subfolder creation.", dirName);
            }
            else
            {
                _logger.LogWarning(
                    "Failed to ensure album '{AlbumName}' for new subfolder: {Error}",
                    dirName,
                    result.ErrorMessage ?? "unknown");
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to handle subfolder creation {Path}.", fullPath);
        }
    }

    private async Task HandleSubdirDeletedAsync(string fullPath)
    {
        try
        {
            var normalizedDir = NormalizeDirectory(fullPath);
            var dirName = Path.GetFileName(normalizedDir);
            if (string.IsNullOrWhiteSpace(dirName))
            {
                return;
            }

            var prefix = normalizedDir + Path.DirectorySeparatorChar;
            var toTrash = new List<string>();
            foreach (var entry in _pathToAssetId.ToArray())
            {
                if (!entry.Key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (_pathToAssetId.TryRemove(entry.Key, out var assetId))
                {
                    _debouncedFiles.TryRemove(entry.Key, out _);
                    toTrash.Add(assetId);
                }
            }

            if (toTrash.Count > 0)
            {
                var trashResult = await _immichAssetClient.TrashAssetsAsync(toTrash, CancellationToken.None);
                if (trashResult.IsSuccess)
                {
                    _logger.LogInformation(
                        "Trashed {Count} asset(s) from deleted subfolder '{DirName}'.",
                        toTrash.Count,
                        dirName);
                }
                else
                {
                    _logger.LogWarning(
                        "Failed to trash {Count} asset(s) from subfolder '{DirName}': {Error}",
                        toTrash.Count,
                        dirName,
                        trashResult.ErrorMessage ?? "unknown");
                }
            }

            var deleteResult = await _immichAssetClient.DeleteAlbumAsync(dirName, CancellationToken.None);
            if (deleteResult.IsSuccess)
            {
                _logger.LogInformation("Deleted album '{AlbumName}' after subfolder removal.", dirName);
            }
            else
            {
                _logger.LogWarning(
                    "Failed to delete album '{AlbumName}' after subfolder removal: {Error}",
                    dirName,
                    deleteResult.ErrorMessage ?? "unknown");
            }

            foreach (var entry in _albumIdToDirName.ToArray())
            {
                if (string.Equals(entry.Value, dirName, StringComparison.Ordinal))
                {
                    _albumIdToDirName.TryRemove(entry.Key, out _);
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to handle subfolder deletion {Path}.", fullPath);
        }
    }

    private async Task HandleSubdirRenamedAsync(string oldFullPath, string newFullPath)
    {
        try
        {
            var oldNormalizedDir = NormalizeDirectory(oldFullPath);
            var newNormalizedDir = NormalizeDirectory(newFullPath);
            var oldDirName = Path.GetFileName(oldNormalizedDir);
            var newDirName = Path.GetFileName(newNormalizedDir);

            if (string.IsNullOrWhiteSpace(newDirName))
            {
                return;
            }

            RekeyPathMapPrefix(oldNormalizedDir, newNormalizedDir);

            if (string.IsNullOrWhiteSpace(oldDirName)
                || string.Equals(oldDirName, newDirName, StringComparison.Ordinal))
            {
                return;
            }

            var rename = await _immichAssetClient.RenameAlbumAsync(oldDirName, newDirName, CancellationToken.None);
            if (rename.IsSuccess && !rename.AlbumMissing)
            {
                if (!string.IsNullOrWhiteSpace(rename.AlbumId))
                {
                    _albumIdToDirName[rename.AlbumId!] = newDirName;
                }

                _logger.LogInformation(
                    "Renamed Immich album '{OldName}' to '{NewName}' after subfolder rename.",
                    oldDirName,
                    newDirName);
                return;
            }

            if (rename.AlbumMissing)
            {
                var ensure = await _immichAssetClient.EnsureAlbumAsync(newDirName, CancellationToken.None);
                if (ensure.IsSuccess)
                {
                    if (!string.IsNullOrWhiteSpace(ensure.AlbumId))
                    {
                        _albumIdToDirName[ensure.AlbumId!] = newDirName;
                    }

                    _logger.LogInformation(
                        "Subfolder renamed '{OldName}' -> '{NewName}'; target album ensured (no source album existed).",
                        oldDirName,
                        newDirName);
                }
                else
                {
                    _logger.LogWarning(
                        "Failed to ensure album '{AlbumName}' after subfolder rename: {Error}",
                        newDirName,
                        ensure.ErrorMessage ?? "unknown");
                }

                return;
            }

            _logger.LogWarning(
                "Failed to rename Immich album '{OldName}' -> '{NewName}': {Error}",
                oldDirName,
                newDirName,
                rename.ErrorMessage ?? "unknown");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to handle subfolder rename {Old} -> {New}.", oldFullPath, newFullPath);
        }
    }

    private void RekeyPathMapPrefix(string oldNormalizedDir, string newNormalizedDir)
    {
        if (string.Equals(oldNormalizedDir, newNormalizedDir, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        var oldPrefix = oldNormalizedDir + Path.DirectorySeparatorChar;
        var newPrefix = newNormalizedDir + Path.DirectorySeparatorChar;

        foreach (var entry in _pathToAssetId.ToArray())
        {
            if (!entry.Key.StartsWith(oldPrefix, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (_pathToAssetId.TryRemove(entry.Key, out var assetId))
            {
                var relative = entry.Key[oldPrefix.Length..];
                _pathToAssetId[newPrefix + relative] = assetId;
            }
        }
    }

    private void TryRenameLocalSubdir(string oldDir, string newDir, string oldName, string newName)
    {
        try
        {
            if (!Directory.Exists(oldDir))
            {
                return;
            }

            if (Directory.Exists(newDir))
            {
                _logger.LogWarning(
                    "Cannot rename local subfolder '{Old}' -> '{New}' to match renamed Immich album: a folder with the new name already exists.",
                    oldName,
                    newName);
                return;
            }

            Directory.Move(oldDir, newDir);
            RekeyPathMapPrefix(oldDir, newDir);

            _logger.LogInformation(
                "Renamed local subfolder '{Old}' -> '{New}' to match renamed Immich album.",
                oldName,
                newName);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(
                ex,
                "Renaming local subfolder '{Old}' -> '{New}' after remote album rename failed.",
                oldName,
                newName);
        }
    }

    private async Task TrashAssetAsync(string assetId, string filePath)
    {
        var result = await _immichAssetClient.TrashAssetsAsync(new[] { assetId }, CancellationToken.None);
        if (result.IsSuccess)
        {
            _logger.LogInformation("Trashed asset {AssetId} on Immich (local {FilePath} removed).", assetId, filePath);
        }
        else
        {
            _logger.LogWarning(
                "Failed to trash asset {AssetId}: {Error}",
                assetId,
                result.ErrorMessage ?? "unknown");
        }
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

                    if (!string.IsNullOrWhiteSpace(result.AssetId))
                    {
                        _pathToAssetId[NormalizePath(request.FilePath)] = result.AssetId!;
                    }

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

    private static string NormalizeDirectory(string path)
    {
        try
        {
            var full = Path.GetFullPath(path);
            return full.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        }
        catch (Exception)
        {
            return path;
        }
    }

    private static string SanitizeDirectoryName(string name)
    {
        if (string.IsNullOrWhiteSpace(name))
        {
            return string.Empty;
        }

        var invalid = Path.GetInvalidFileNameChars();
        var buffer = new char[name.Length];
        for (var i = 0; i < name.Length; i++)
        {
            buffer[i] = Array.IndexOf(invalid, name[i]) >= 0 ? '_' : name[i];
        }

        return new string(buffer).Trim();
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

    private sealed class WatchSourceContext
    {
        public WatchSourceContext(
            WatchSourceSettings source,
            string syncMode,
            WatchSourceFileFilter filter,
            string normalizedRoot,
            bool useSubdirsAsAlbums,
            bool useFlatAlbum,
            bool effectiveIncludeSubdirectories)
        {
            Source = source;
            SyncMode = syncMode;
            Filter = filter;
            NormalizedRoot = normalizedRoot;
            UseSubdirsAsAlbums = useSubdirsAsAlbums;
            UseFlatAlbum = useFlatAlbum;
            EffectiveIncludeSubdirectories = effectiveIncludeSubdirectories;
        }

        public WatchSourceSettings Source { get; }

        public string SyncMode { get; }

        public WatchSourceFileFilter Filter { get; }

        public string NormalizedRoot { get; }

        public bool UseSubdirsAsAlbums { get; }

        public bool UseFlatAlbum { get; }

        public bool EffectiveIncludeSubdirectories { get; }

        public bool IsSyncMode => string.Equals(SyncMode, WatchSourceSyncModes.Sync, StringComparison.Ordinal);
    }
}
