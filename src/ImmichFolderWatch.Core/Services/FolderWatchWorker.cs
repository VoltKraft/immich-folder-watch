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
    private static readonly StringComparer PathComparer = OperatingSystem.IsWindows()
        ? StringComparer.OrdinalIgnoreCase
        : StringComparer.Ordinal;

    private static readonly StringComparison PathComparison = OperatingSystem.IsWindows()
        ? StringComparison.OrdinalIgnoreCase
        : StringComparison.Ordinal;

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

    private readonly Dictionary<string, Dictionary<string, FileFingerprint>> _pollingBaseline =
        new(PathComparer);

    private DateTimeOffset _lastPollingSweep = DateTimeOffset.MinValue;

    private readonly AppConfig _config;

    private readonly IFileReadinessChecker _fileReadinessChecker;

    private readonly IUploadBatchQueue _uploadBatchQueue;

    private readonly IImmichAssetClient _immichAssetClient;

    private readonly ISyncStateStore _syncStateStore;

    private readonly string _accountScope;

    private readonly IImmichRealtimeClient? _immichRealtimeClient;

    private readonly SyncStatusProvider _syncStatusProvider;

    private readonly ILogger<FolderWatchWorker> _logger;

    private volatile int _pullRequested;

    private readonly ConcurrentDictionary<string, PendingFile> _debouncedFiles = new(PathComparer);

    private readonly ConcurrentDictionary<string, string> _pathToAssetId = new(PathComparer);

    private readonly ConcurrentDictionary<string, SyncStateEntry> _stateByPath = new(PathComparer);

    private readonly ConcurrentDictionary<string, byte> _downloadsInProgress = new(PathComparer);

    private readonly ConcurrentDictionary<string, DateTimeOffset> _remoteDeletesInProgress = new(PathComparer);

    /// <summary>
    /// Asset ids we just trashed locally — tombstone so a subsequent
    /// pull that still sees the asset (race against Immich's trash
    /// propagation) does not re-download it. Set OPTIMISTICALLY in
    /// the synchronous prefix of HandleDeleteInSyncAsync so a pull
    /// that fires on the same loop tick as the sweep already sees
    /// the tombstone. Rolled back if TrashAssetsAsync fails. Entries
    /// expire after <see cref="TombstoneTtl"/>.
    /// </summary>
    private readonly ConcurrentDictionary<string, DateTimeOffset> _recentlyTrashedAssetIds =
        new(StringComparer.Ordinal);

    /// <summary>
    /// Local paths whose file the user just deleted. Tombstoned even
    /// when no asset id was mapped (rare, but happens if the file was
    /// hand-copied into the watch dir without going through the upload
    /// pipeline) so DownloadAssetsAsync still skips re-creating the
    /// path. Asset stays on Immich in that case — the warn log tells
    /// the user.
    /// </summary>
    private readonly ConcurrentDictionary<string, DateTimeOffset> _recentlyDeletedPaths =
        new(PathComparer);

    private static readonly TimeSpan TombstoneTtl = TimeSpan.FromSeconds(120);

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
        ISyncStateStore syncStateStore,
        SyncStatusProvider syncStatusProvider,
        ILogger<FolderWatchWorker> logger,
        IImmichRealtimeClient? immichRealtimeClient = null)
    {
        _config = config;
        _fileReadinessChecker = fileReadinessChecker;
        _uploadBatchQueue = uploadBatchQueue;
        _immichAssetClient = immichAssetClient;
        _syncStateStore = syncStateStore;
        _accountScope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        _immichRealtimeClient = immichRealtimeClient;
        _syncStatusProvider = syncStatusProvider;
        _logger = logger;
        _batchInterval = TimeSpan.FromSeconds(config.Watch.BatchIntervalSeconds);
        _fileReadyTimeout = TimeSpan.FromSeconds(config.Watch.FileReadyTimeoutSeconds);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            await _syncStateStore.InitializeAsync(stoppingToken);
            await _syncStateStore.DeleteExpiredTombstonesAsync(DateTimeOffset.UtcNow, stoppingToken);
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            return;
        }
        catch (Exception ex)
        {
            _logger.LogCritical(
                ex,
                "Synchronization is disabled because the state database could not be opened: {DatabasePath}",
                _syncStateStore.DatabasePath);
            return;
        }

        RegisterWatchers();

        _logger.LogInformation("Folder watcher started with {SourceCount} source(s).", _watchers.Count);

        if (_immichRealtimeClient is not null)
        {
            _immichRealtimeClient.RemoteChangeDetected += OnRemoteChangeDetected;
            _ = Task.Run(() => _immichRealtimeClient.StartAsync(stoppingToken), stoppingToken);
        }

        await LoadPersistedStateAsync(stoppingToken);
        await ReconcileExistingFilesAsync(stoppingToken, deferUnknownSyncFiles: true);
        await PullFromImmichAsync(stoppingToken);
        await ReconcileExistingFilesAsync(stoppingToken, deferUnknownSyncFiles: false);

        using var loopTimer = new PeriodicTimer(TimeSpan.FromSeconds(1));
        var lastFlush = DateTimeOffset.UtcNow;
        var lastAlbumPull = DateTimeOffset.UtcNow;

        try
        {
            while (await loopTimer.WaitForNextTickAsync(stoppingToken))
            {
                if (DateTimeOffset.UtcNow - _lastPollingSweep >= PollingSweepInterval)
                {
                    await PollDirectoriesForChangesAsync(stoppingToken);
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
                    // Always sweep right before pulling: an Immich-side
                    // realtime event can fire pullRequested within
                    // milliseconds of a local delete, racing ahead of
                    // the regular 5 s sweep gate. Running the sweep
                    // here guarantees HandleDeleteInSyncAsync sets the
                    // asset-id + path tombstones (synchronously, before
                    // its first await) before the pull's
                    // DownloadAssetsAsync iterates assets.
                    await PollDirectoriesForChangesAsync(stoppingToken);
                    _lastPollingSweep = DateTimeOffset.UtcNow;

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
                EnableRaisingEvents = false,
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
            _pollingBaseline[NormalizePath(source.Path)] = new Dictionary<string, FileFingerprint>(PathComparer);
            watcher.EnableRaisingEvents = true;
            _logger.LogInformation(
                "Polling watcher registered for {Path}; the persistent baseline will be reconciled in the background (sweep interval = {SweepSeconds}s).",
                source.Path,
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

    private async Task LoadPersistedStateAsync(CancellationToken cancellationToken)
    {
        foreach (var context in _sources)
        {
            var entries = await _syncStateStore.GetSourceEntriesAsync(
                _accountScope,
                context.NormalizedRoot,
                cancellationToken);

            foreach (var entry in entries)
            {
                var fullPath = NormalizePath(Path.Combine(context.NormalizedRoot, entry.RelativePath));
                if (entry.Status == SyncEntryStatus.Tombstone)
                {
                    if (entry.TombstoneExpiresAtUtc > DateTimeOffset.UtcNow)
                    {
                        _recentlyDeletedPaths[fullPath] = entry.LastSynchronizedAtUtc;
                        if (!string.IsNullOrWhiteSpace(entry.AssetId))
                        {
                            _recentlyTrashedAssetIds[entry.AssetId] = entry.LastSynchronizedAtUtc;
                        }
                    }

                    continue;
                }

                _stateByPath[fullPath] = entry;
                if (!string.IsNullOrWhiteSpace(entry.AssetId))
                {
                    _pathToAssetId[fullPath] = entry.AssetId;
                }
            }
        }
    }

    private async Task ReconcileExistingFilesAsync(
        CancellationToken cancellationToken,
        bool deferUnknownSyncFiles)
    {
        foreach (var context in _sources)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var snapshot = new Dictionary<string, FileFingerprint>(PathComparer);
            var seen = new HashSet<string>(PathComparer);

            var queuedCount = 0;
            try
            {
                var searchOption = context.EffectiveIncludeSubdirectories
                    ? SearchOption.AllDirectories
                    : SearchOption.TopDirectoryOnly;

                foreach (var filePath in Directory.EnumerateFiles(context.Source.Path, "*", searchOption))
                {
                    var normalized = NormalizePath(filePath);
                    seen.Add(normalized);
                    if (!context.Filter.IsMatch(filePath))
                    {
                        continue;
                    }

                    if (!TryGetFingerprint(normalized, out var fingerprint))
                    {
                        continue;
                    }

                    snapshot[normalized] = fingerprint;
                    seen.Add(normalized);
                    var albumName = GetEffectiveAlbum(context, normalized);

                    var hasPersistedState = _stateByPath.TryGetValue(normalized, out var existing);
                    if (hasPersistedState
                        && existing is not null
                        && existing.Status == SyncEntryStatus.Synchronized
                        && fingerprint.Matches(existing))
                    {
                        if (!string.Equals(existing.AlbumName, albumName, StringComparison.Ordinal))
                        {
                            await ReconcileAlbumAsync(context, normalized, albumName, existing, cancellationToken);
                        }

                        continue;
                    }

                    if (context.IsSyncMode && deferUnknownSyncFiles && !hasPersistedState)
                    {
                        continue;
                    }

                    if (string.Equals(context.SyncMode, WatchSourceSyncModes.UploadNew, StringComparison.Ordinal))
                    {
                        continue;
                    }

                    if (_uploadBatchQueue.TryEnqueue(
                        new UploadAssetRequest(normalized, albumName, context.NormalizedRoot)))
                    {
                        queuedCount++;
                    }
                }
            }
            catch (Exception ex)
            {
                context.RemoteDeleteSafe = false;
                _logger.LogWarning(ex, "Initial scan failed for source {Path}.", context.Source.Path);
                continue;
            }

            _pollingBaseline[NormalizePath(context.Source.Path)] = snapshot;

            var persisted = _stateByPath
                .Where(pair => IsPathCoveredByContext(context, pair.Key))
                .Select(pair => pair.Key)
                .Where(path => !seen.Contains(path))
                .ToList();
            foreach (var missingPath in persisted)
            {
                if (context.IsSyncMode)
                {
                    await HandleDeleteInSyncAsync(context, missingPath);
                }
                else
                {
                    await DeletePersistedStateAsync(context, missingPath, cancellationToken);
                }
            }

            _logger.LogInformation(
                "Persistent reconciliation for {SyncMode} queued {Count} changed file(s) from {Path}.",
                context.SyncMode,
                queuedCount,
                context.Source.Path);
        }

        _syncStatusProvider.ReportPendingCount(_uploadBatchQueue.Count);
    }

    private async Task ReconcileAlbumAsync(
        WatchSourceContext context,
        string fullPath,
        string albumName,
        SyncStateEntry existing,
        CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(albumName) && !string.IsNullOrWhiteSpace(existing.AssetId))
        {
            var result = await _immichAssetClient.AddAssetsToAlbumAsync(
                albumName,
                new[] { existing.AssetId },
                cancellationToken);
            if (!result.IsSuccess)
            {
                context.RemoteDeleteSafe = false;
                _logger.LogWarning(
                    "Album-only reconciliation failed for {FilePath}: {Error}",
                    fullPath,
                    result.ErrorMessage ?? "unknown");
                return;
            }
        }

        var updated = existing with
        {
            AlbumName = albumName,
            LastSynchronizedAtUtc = DateTimeOffset.UtcNow,
        };
        await _syncStateStore.UpsertAsync(updated, cancellationToken);
        _stateByPath[fullPath] = updated;
    }

    private async Task PollDirectoriesForChangesAsync(CancellationToken cancellationToken)
    {
        foreach (var marker in _remoteDeletesInProgress.ToArray())
        {
            if (DateTimeOffset.UtcNow - marker.Value > TombstoneTtl)
            {
                _remoteDeletesInProgress.TryRemove(marker.Key, out _);
            }
        }

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

            Dictionary<string, FileFingerprint> current;
            try
            {
                current = new Dictionary<string, FileFingerprint>(PathComparer);
                foreach (var filePath in Directory.EnumerateFiles(context.Source.Path, "*", searchOption))
                {
                    var normalized = NormalizePath(filePath);
                    if (!TryGetFingerprint(normalized, out var fingerprint))
                    {
                        continue;
                    }

                    current[normalized] = fingerprint;
                    if (known.TryGetValue(normalized, out var previous) && previous == fingerprint)
                    {
                        continue;
                    }

                    if (!context.Filter.IsMatch(normalized))
                    {
                        continue;
                    }

                    _logger.LogInformation("Polling sweep detected new or changed file: {Path}", normalized);
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
            var disappeared = known.Keys.Where(path => !current.ContainsKey(path)).ToList();
            foreach (var path in disappeared)
            {
                if (!context.Filter.IsMatch(path))
                {
                    continue;
                }
                _logger.LogInformation("Polling sweep detected removed file: {Path}", path);
                if (context.IsSyncMode)
                {
                    await HandleDeleteInSyncAsync(context, path);
                }
                else
                {
                    _debouncedFiles.TryRemove(path, out _);
                    _pathToAssetId.TryRemove(path, out _);
                    await DeletePersistedStateAsync(context, path, cancellationToken);
                }
            }

            _pollingBaseline[sourceKey] = current;
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

            if (pullSucceeded && context.RemoteDeleteSafe)
            {
                await PropagateRemoteDeletesAsync(context, remoteAssetIds, cancellationToken);
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
    private async Task PropagateRemoteDeletesAsync(
        WatchSourceContext context,
        HashSet<string> remoteAssetIds,
        CancellationToken cancellationToken)
    {
        var sourceKey = NormalizePath(context.Source.Path);
        _pollingBaseline.TryGetValue(sourceKey, out var baseline);

        var stale = _stateByPath
            .Where(entry =>
                IsPathWithinSource(context, entry.Key)
                && entry.Value.Status == SyncEntryStatus.Synchronized
                && !string.IsNullOrWhiteSpace(entry.Value.AssetId)
                && !remoteAssetIds.Contains(entry.Value.AssetId))
            .ToList();

        foreach (var entry in stale)
        {
            try
            {
                var tombstone = entry.Value with
                {
                    Status = SyncEntryStatus.Tombstone,
                    LastSynchronizedAtUtc = DateTimeOffset.UtcNow,
                    TombstoneExpiresAtUtc = DateTimeOffset.UtcNow + TombstoneTtl,
                };
                await _syncStateStore.UpsertAsync(tombstone, cancellationToken);

                if (File.Exists(entry.Key))
                {
                    _remoteDeletesInProgress[entry.Key] = DateTimeOffset.UtcNow;
                    File.Delete(entry.Key);
                    _logger.LogInformation(
                        "Removed local file after remote delete (asset {AssetId} no longer on Immich): {Path}",
                        entry.Value.AssetId,
                        entry.Key);
                }

                _pathToAssetId.TryRemove(entry.Key, out _);
                _stateByPath.TryRemove(entry.Key, out _);
                baseline?.Remove(entry.Key);
                _debouncedFiles.TryRemove(entry.Key, out _);
                await _syncStateStore.DeleteAsync(
                    _accountScope,
                    context.NormalizedRoot,
                    entry.Value.RelativePath,
                    cancellationToken);
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
                await TryRenameLocalSubdirAsync(context, previousDir, targetDir, previousDirName, sanitized, cancellationToken);
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

            // Tombstone: a local delete just trashed this asset and the
            // pull is still seeing it. Don't recreate the path mapping
            // and don't re-download — let the trash propagate on Immich.
            if (IsRecentlyTrashed(asset.Id))
            {
                _logger.LogDebug(
                    "Skipping recently-trashed asset {AssetId} during sync pull.",
                    asset.Id);
                continue;
            }

            var destinationPath = Path.Combine(targetDirectory, asset.OriginalFileName);
            var normalized = NormalizePath(destinationPath);

            // Path-level tombstone catches the rare case where the
            // sweep fired but the asset id wasn't mapped — pull would
            // otherwise re-create a file the user just deleted.
            if (IsPathRecentlyDeleted(normalized))
            {
                _logger.LogDebug(
                    "Skipping recently-deleted local path during sync pull: {Path}",
                    normalized);
                continue;
            }

            if (!context.Filter.IsMatch(destinationPath))
            {
                continue;
            }

            if (File.Exists(destinationPath))
            {
                if (TryGetFingerprint(normalized, out var existingFingerprint))
                {
                    var effectiveAlbum = GetEffectiveAlbum(context, normalized);
                    if (_stateByPath.TryGetValue(normalized, out var currentState)
                        && currentState.Status == SyncEntryStatus.Synchronized)
                    {
                        if (!existingFingerprint.Matches(currentState))
                        {
                            // The local file changed while the app was stopped.
                            // Keep the old fingerprint so the queued local change
                            // remains distinguishable from the remote asset.
                            continue;
                        }

                        if (!string.Equals(currentState.AssetId, asset.Id, StringComparison.Ordinal))
                        {
                            // Multiple Immich assets can have the same original
                            // file name. Keep the mapping that was confirmed for
                            // this local file instead of replacing it according to
                            // the server's enumeration order.
                            continue;
                        }

                        _pathToAssetId[normalized] = asset.Id;
                        if (string.Equals(currentState.AlbumName, effectiveAlbum, StringComparison.Ordinal))
                        {
                            continue;
                        }
                    }

                    var entry = CreateSynchronizedEntry(
                        context,
                        normalized,
                        asset.Id,
                        effectiveAlbum,
                        existingFingerprint,
                        SyncTransferDirection.Download);
                    await _syncStateStore.UpsertAsync(entry, cancellationToken);
                    _stateByPath[normalized] = entry;
                    _pathToAssetId[normalized] = asset.Id;
                }

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
                var normalized = NormalizePath(destinationPath);
                _downloadsInProgress[normalized] = 0;
                try
                {
                    var download = await _immichAssetClient.DownloadAssetAsync(asset.Id, destinationPath, cancellationToken);
                    if (download.IsSuccess && TryGetFingerprint(normalized, out var fingerprint))
                    {
                        var entry = CreateSynchronizedEntry(
                            context,
                            normalized,
                            asset.Id,
                            GetEffectiveAlbum(context, normalized),
                            fingerprint,
                            SyncTransferDirection.Download);
                        await _syncStateStore.UpsertAsync(entry, cancellationToken);
                        _stateByPath[normalized] = entry;
                        _pathToAssetId[normalized] = asset.Id;
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
                            download.ErrorMessage ?? "download completed without a readable destination file");
                    }
                }
                finally
                {
                    _downloadsInProgress.TryRemove(normalized, out _);
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
        if (_downloadsInProgress.ContainsKey(normalizedPath))
        {
            return;
        }

        if (_stateByPath.TryGetValue(normalizedPath, out var synchronized)
            && synchronized.Status == SyncEntryStatus.Synchronized
            && TryGetFingerprint(normalizedPath, out var fingerprint)
            && fingerprint.Matches(synchronized))
        {
            return;
        }

        var albumName = GetEffectiveAlbum(context, normalizedPath);
        var timestamp = DateTimeOffset.UtcNow;

        _debouncedFiles.AddOrUpdate(
            normalizedPath,
            _ => new PendingFile(albumName, context.NormalizedRoot, timestamp),
            (_, _) => new PendingFile(albumName, context.NormalizedRoot, timestamp));

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
                            _pathToAssetId[oldNormalized] = assetId!;
                            return;
                        }
                    }

                    _logger.LogInformation(
                        "Asset {AssetId} was added to album '{NewAlbum}' after local move ({OldPath} -> {NewPath}); existing album memberships were preserved.",
                        assetId,
                        string.IsNullOrWhiteSpace(newAlbum) ? "(unassigned)" : newAlbum,
                        oldNormalized,
                        newNormalized);
                }

                _pathToAssetId[newNormalized] = assetId!;
                if (TryGetFingerprint(newNormalized, out var renamedFingerprint))
                {
                    if (_stateByPath.TryRemove(oldNormalized, out var oldState))
                    {
                        await _syncStateStore.DeleteAsync(
                            _accountScope,
                            context.NormalizedRoot,
                            oldState.RelativePath,
                            CancellationToken.None);
                    }

                    var renamedState = CreateSynchronizedEntry(
                        context,
                        newNormalized,
                        assetId,
                        newAlbum,
                        renamedFingerprint,
                        oldState?.Direction ?? SyncTransferDirection.Upload);
                    await _syncStateStore.UpsertAsync(renamedState, CancellationToken.None);
                    _stateByPath[newNormalized] = renamedState;
                }
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

            if (_remoteDeletesInProgress.TryRemove(normalized, out _))
            {
                return;
            }

            // Path-level tombstone fires regardless of whether we have
            // an asset id — protects against a pull that races ahead
            // of the sweep (e.g. realtime trigger right after delete)
            // re-creating the file at the same path.
            _recentlyDeletedPaths[normalized] = DateTimeOffset.UtcNow;

            _stateByPath.TryGetValue(normalized, out var previousState);
            var hadAssetId = _pathToAssetId.TryGetValue(normalized, out var assetId);
            if (hadAssetId)
            {
                _recentlyTrashedAssetIds[assetId!] = DateTimeOffset.UtcNow;
            }

            var tombstone = (previousState ?? CreateTombstoneEntry(context, normalized, assetId)) with
            {
                AssetId = assetId ?? previousState?.AssetId,
                Status = SyncEntryStatus.Tombstone,
                LastSynchronizedAtUtc = DateTimeOffset.UtcNow,
                TombstoneExpiresAtUtc = DateTimeOffset.UtcNow + TombstoneTtl,
            };
            await _syncStateStore.UpsertAsync(tombstone, CancellationToken.None);
            _stateByPath.TryRemove(normalized, out _);
            _pathToAssetId.TryRemove(normalized, out _);

            if (!hadAssetId)
            {
                _logger.LogWarning(
                    "Local delete detected but no Immich asset id was mapped for {FilePath}; the asset (if any) was NOT trashed on Immich. Re-download is suppressed for {Ttl}s.",
                    normalized,
                    (int)TombstoneTtl.TotalSeconds);
                return;
            }

            var trashed = await TrashAssetAsync(assetId!, normalized);
            if (!trashed && previousState is not null)
            {
                await _syncStateStore.UpsertAsync(previousState, CancellationToken.None);
                _stateByPath[normalized] = previousState;
                _pathToAssetId[normalized] = assetId!;
            }
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

            var sourceContext = FindSourceContext(string.Empty, normalizedDir);
            if (sourceContext is not null)
            {
                await TombstonePersistedStatePrefixAsync(sourceContext, normalizedDir, CancellationToken.None);
            }

            var prefix = normalizedDir + Path.DirectorySeparatorChar;
            var toTrash = new List<string>();
            foreach (var entry in _pathToAssetId.ToArray())
            {
                if (!entry.Key.StartsWith(prefix, PathComparison))
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
            var sourceContext = FindSourceContext(string.Empty, newNormalizedDir);
            if (sourceContext is not null)
            {
                await RekeyPersistedStatePrefixAsync(
                    sourceContext,
                    oldNormalizedDir,
                    newNormalizedDir,
                    CancellationToken.None);
            }

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
        if (string.Equals(oldNormalizedDir, newNormalizedDir, PathComparison))
        {
            return;
        }

        var oldPrefix = oldNormalizedDir + Path.DirectorySeparatorChar;
        var newPrefix = newNormalizedDir + Path.DirectorySeparatorChar;

        foreach (var entry in _pathToAssetId.ToArray())
        {
            if (!entry.Key.StartsWith(oldPrefix, PathComparison))
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

    private async Task TryRenameLocalSubdirAsync(
        WatchSourceContext context,
        string oldDir,
        string newDir,
        string oldName,
        string newName,
        CancellationToken cancellationToken)
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
            await RekeyPersistedStatePrefixAsync(context, oldDir, newDir, cancellationToken);

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

    private async Task<bool> TrashAssetAsync(string assetId, string filePath)
    {
        // Tombstone is set by the caller (HandleDeleteInSyncAsync) BEFORE
        // we run, so a pull racing on the same loop tick already sees
        // the asset id as recently-trashed. Roll the tombstone back if
        // the network call fails so a future retry can still propagate.
        var result = await _immichAssetClient.TrashAssetsAsync(new[] { assetId }, CancellationToken.None);
        if (result.IsSuccess)
        {
            _logger.LogInformation("Trashed asset {AssetId} on Immich (local {FilePath} removed).", assetId, filePath);
            return true;
        }

        _recentlyTrashedAssetIds.TryRemove(assetId, out _);
        _logger.LogWarning(
            "Failed to trash asset {AssetId}: {Error}",
            assetId,
            result.ErrorMessage ?? "unknown");
        return false;
    }

    /// <summary>
    /// True iff the asset id was just trashed locally and the tombstone
    /// hasn't expired yet. Lazy-prunes the entry on read.
    /// </summary>
    private bool IsRecentlyTrashed(string assetId)
    {
        if (string.IsNullOrEmpty(assetId))
        {
            return false;
        }

        if (!_recentlyTrashedAssetIds.TryGetValue(assetId, out var trashedAt))
        {
            return false;
        }

        if (DateTimeOffset.UtcNow - trashedAt > TombstoneTtl)
        {
            _recentlyTrashedAssetIds.TryRemove(assetId, out _);
            return false;
        }

        return true;
    }

    /// <summary>
    /// True iff the local file at <paramref name="path"/> was just
    /// deleted by the user and the tombstone hasn't expired yet.
    /// Lazy-prunes the entry on read.
    /// </summary>
    private bool IsPathRecentlyDeleted(string path)
    {
        if (string.IsNullOrEmpty(path))
        {
            return false;
        }

        if (!_recentlyDeletedPaths.TryGetValue(path, out var deletedAt))
        {
            return false;
        }

        if (DateTimeOffset.UtcNow - deletedAt > TombstoneTtl)
        {
            _recentlyDeletedPaths.TryRemove(path, out _);
            return false;
        }

        return true;
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
                var context = FindSourceContext(pendingFile.SourcePath, path);
                if (context is not null)
                {
                    OnFileEvent(context, path);
                }
                continue;
            }

            if (_stateByPath.TryGetValue(path, out var synchronized)
                && synchronized.Status == SyncEntryStatus.Synchronized
                && TryGetFingerprint(path, out var fingerprint)
                && fingerprint.Matches(synchronized))
            {
                continue;
            }

            var queued = _uploadBatchQueue.TryEnqueue(
                new UploadAssetRequest(path, pendingFile.AlbumName, pendingFile.SourcePath));
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

                var context = FindSourceContext(request.SourcePath, request.FilePath);
                if (context is null || !TryGetFingerprint(request.FilePath, out var uploadedFingerprint))
                {
                    _logger.LogWarning("Skipping upload because its watch source or file metadata is unavailable: {FilePath}", request.FilePath);
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

                    if (!TryGetFingerprint(request.FilePath, out var currentFingerprint)
                        || currentFingerprint != uploadedFingerprint)
                    {
                        _logger.LogInformation(
                            "File changed while it was being uploaded and will be queued again: {FilePath}",
                            request.FilePath);
                        OnFileEvent(context, request.FilePath);
                    }
                    else
                    {
                        var normalizedPath = NormalizePath(request.FilePath);
                        var entry = CreateSynchronizedEntry(
                            context,
                            normalizedPath,
                            result.AssetId,
                            request.AlbumName,
                            currentFingerprint,
                            SyncTransferDirection.Upload);
                        await _syncStateStore.UpsertAsync(entry, cancellationToken);
                        _stateByPath[normalizedPath] = entry;
                        if (!string.IsNullOrWhiteSpace(result.AssetId))
                        {
                            _pathToAssetId[normalizedPath] = result.AssetId!;
                        }
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
                    OnFileEvent(context, request.FilePath);
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
            var root = Path.GetPathRoot(full);
            return string.Equals(full, root, PathComparison)
                ? full
                : full.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
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

    private static bool TryGetFingerprint(string path, out FileFingerprint fingerprint)
    {
        try
        {
            var file = new FileInfo(path);
            file.Refresh();
            if (!file.Exists)
            {
                fingerprint = default;
                return false;
            }

            fingerprint = new FileFingerprint(file.Length, file.LastWriteTimeUtc.Ticks);
            return true;
        }
        catch (Exception)
        {
            fingerprint = default;
            return false;
        }
    }

    private SyncStateEntry CreateSynchronizedEntry(
        WatchSourceContext context,
        string fullPath,
        string? assetId,
        string albumName,
        FileFingerprint fingerprint,
        SyncTransferDirection direction) =>
        new(
            _accountScope,
            context.NormalizedRoot,
            GetRelativePath(context, fullPath),
            assetId,
            albumName,
            fingerprint.FileSize,
            new DateTimeOffset(fingerprint.LastWriteTimeUtcTicks, TimeSpan.Zero),
            direction,
            SyncEntryStatus.Synchronized,
            DateTimeOffset.UtcNow);

    private SyncStateEntry CreateTombstoneEntry(
        WatchSourceContext context,
        string fullPath,
        string? assetId) =>
        new(
            _accountScope,
            context.NormalizedRoot,
            GetRelativePath(context, fullPath),
            assetId,
            GetEffectiveAlbum(context, fullPath),
            0,
            DateTimeOffset.UnixEpoch,
            SyncTransferDirection.Upload,
            SyncEntryStatus.Tombstone,
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow + TombstoneTtl);

    private static string GetRelativePath(WatchSourceContext context, string fullPath)
    {
        var relative = Path.GetRelativePath(context.NormalizedRoot, fullPath);
        if (Path.IsPathRooted(relative)
            || string.Equals(relative, "..", StringComparison.Ordinal)
            || relative.StartsWith($"..{Path.DirectorySeparatorChar}", StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"File '{fullPath}' is outside watch source '{context.NormalizedRoot}'.");
        }

        return relative;
    }

    private static bool IsPathWithinSource(WatchSourceContext context, string fullPath)
    {
        if (string.Equals(fullPath, context.NormalizedRoot, PathComparison))
        {
            return true;
        }

        var prefix = Path.EndsInDirectorySeparator(context.NormalizedRoot)
            ? context.NormalizedRoot
            : context.NormalizedRoot + Path.DirectorySeparatorChar;
        return fullPath.StartsWith(prefix, PathComparison);
    }

    private static bool IsPathCoveredByContext(WatchSourceContext context, string fullPath)
    {
        if (!IsPathWithinSource(context, fullPath))
        {
            return false;
        }

        if (context.EffectiveIncludeSubdirectories)
        {
            return true;
        }

        var directory = Path.GetDirectoryName(fullPath);
        return string.Equals(directory, context.NormalizedRoot, PathComparison);
    }

    private WatchSourceContext? FindSourceContext(string sourcePath, string filePath)
    {
        if (!string.IsNullOrWhiteSpace(sourcePath))
        {
            var normalizedSource = NormalizeDirectory(sourcePath);
            var exact = _sources.FirstOrDefault(source =>
                string.Equals(source.NormalizedRoot, normalizedSource, PathComparison));
            if (exact is not null)
            {
                return exact;
            }
        }

        var normalizedFile = NormalizePath(filePath);
        return _sources
            .Where(source => IsPathWithinSource(source, normalizedFile))
            .OrderByDescending(source => source.NormalizedRoot.Length)
            .FirstOrDefault();
    }

    private async Task DeletePersistedStateAsync(
        WatchSourceContext context,
        string fullPath,
        CancellationToken cancellationToken)
    {
        if (_stateByPath.TryRemove(fullPath, out var existing))
        {
            await _syncStateStore.DeleteAsync(
                _accountScope,
                context.NormalizedRoot,
                existing.RelativePath,
                cancellationToken);
        }
    }

    private async Task RekeyPersistedStatePrefixAsync(
        WatchSourceContext context,
        string oldDirectory,
        string newDirectory,
        CancellationToken cancellationToken)
    {
        var oldPrefix = NormalizeDirectory(oldDirectory) + Path.DirectorySeparatorChar;
        var newPrefix = NormalizeDirectory(newDirectory) + Path.DirectorySeparatorChar;
        var affected = _stateByPath
            .Where(entry => entry.Key.StartsWith(oldPrefix, PathComparison))
            .ToList();

        foreach (var entry in affected)
        {
            var suffix = entry.Key[oldPrefix.Length..];
            var newPath = NormalizePath(newPrefix + suffix);
            await _syncStateStore.DeleteAsync(
                _accountScope,
                context.NormalizedRoot,
                entry.Value.RelativePath,
                cancellationToken);
            var updated = entry.Value with
            {
                RelativePath = GetRelativePath(context, newPath),
                AlbumName = GetEffectiveAlbum(context, newPath),
                LastSynchronizedAtUtc = DateTimeOffset.UtcNow,
            };
            await _syncStateStore.UpsertAsync(updated, cancellationToken);
            _stateByPath.TryRemove(entry.Key, out _);
            _stateByPath[newPath] = updated;
        }
    }

    private async Task TombstonePersistedStatePrefixAsync(
        WatchSourceContext context,
        string directory,
        CancellationToken cancellationToken)
    {
        var prefix = NormalizeDirectory(directory) + Path.DirectorySeparatorChar;
        var affected = _stateByPath
            .Where(entry => entry.Key.StartsWith(prefix, PathComparison))
            .ToList();

        foreach (var entry in affected)
        {
            var tombstone = entry.Value with
            {
                Status = SyncEntryStatus.Tombstone,
                LastSynchronizedAtUtc = DateTimeOffset.UtcNow,
                TombstoneExpiresAtUtc = DateTimeOffset.UtcNow + TombstoneTtl,
            };
            await _syncStateStore.UpsertAsync(tombstone, cancellationToken);
            _stateByPath.TryRemove(entry.Key, out _);
            _recentlyDeletedPaths[entry.Key] = tombstone.LastSynchronizedAtUtc;
            if (!string.IsNullOrWhiteSpace(tombstone.AssetId))
            {
                _recentlyTrashedAssetIds[tombstone.AssetId] = tombstone.LastSynchronizedAtUtc;
            }
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

    private sealed record PendingFile(string AlbumName, string SourcePath, DateTimeOffset LastEventUtc);

    private readonly record struct FileFingerprint(long FileSize, long LastWriteTimeUtcTicks)
    {
        public bool Matches(SyncStateEntry entry) =>
            FileSize == entry.FileSize
            && LastWriteTimeUtcTicks == entry.LastWriteTimeUtc.UtcDateTime.Ticks;
    }

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

        public bool RemoteDeleteSafe { get; set; } = true;
    }
}
