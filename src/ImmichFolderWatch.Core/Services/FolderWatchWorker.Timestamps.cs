using System.Security.Cryptography;
using ImmichFolderWatch.Core.Models;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Core.Services;

public sealed partial class FolderWatchWorker
{
    private async Task RecoverTimestampRepairsAsync(CancellationToken cancellationToken)
    {
        try
        {
            foreach (var context in _sources)
            {
                var repairs = await _syncStateStore.GetTimestampRepairsAsync(
                    _accountScope, context.NormalizedRoot, cancellationToken);
                foreach (var repair in repairs)
                    await ResumeTimestampRepairAsync(context, repair, cancellationToken);
            }
        }
        catch (Exception ex)
        {
            // Recovery precedes reconciliation: a partially changed mtime must
            // never be interpreted as a local edit and sent back to Immich.
            throw new TimestampRepairException(ex);
        }
    }

    private async Task<SyncStateEntry> CorrectDownloadedTimestampsAsync(
        WatchSourceContext context, string path, AlbumAssetSummary asset,
        SyncStateEntry entry, CancellationToken cancellationToken)
    {
        if (entry.Direction != SyncTransferDirection.Download
            || DownloadedFileTimestamps.GetDesired(asset) is not { } desired
            || TimestampsMatch(path, desired)
            || new FileInfo(path).LinkTarget is not null)
            return entry;

        try
        {
            var hash = await HashFileAsync(path, cancellationToken);
            if (!TryGetFingerprint(path, out var fingerprint) || !fingerprint.Matches(entry)) return entry;
            var repair = new SyncTimestampRepair(entry, desired.CreationTimeUtc, desired.LastWriteTimeUtc, hash);
            await _syncStateStore.SaveTimestampRepairAsync(repair, cancellationToken);
            return await ResumeTimestampRepairAsync(context, repair, cancellationToken) ?? entry;
        }
        catch (Exception ex)
        {
            throw new TimestampRepairException(ex);
        }
    }

    private async Task<SyncStateEntry?> ResumeTimestampRepairAsync(
        WatchSourceContext context, SyncTimestampRepair repair, CancellationToken cancellationToken)
    {
        var original = repair.OriginalEntry;
        var path = NormalizePath(Path.Combine(context.NormalizedRoot, original.RelativePath));
        _ = GetRelativePath(context, path);
        _downloadsInProgress[path] = 0;
        try
        {
            var desired = new DownloadedFileTimestampValues(repair.CreationTimeUtc, repair.LastWriteTimeUtc);
            // The journal includes a content digest so a user edit made after
            // an interrupted repair cannot be silently accepted as synchronized.
            if (!_stateByPath.TryGetValue(path, out var current) || current != original
                || !TryGetFingerprint(path, out var before) || before.FileSize != original.FileSize
                || new FileInfo(path).LinkTarget is not null
                || (!before.Matches(original) && !TimestampMatches(before.LastWriteTimeUtcTicks, desired.LastWriteTimeUtc)))
            {
                await _syncStateStore.CompleteTimestampRepairAsync(repair, null, cancellationToken);
                return null;
            }

            if (await HashFileAsync(path, cancellationToken) != repair.ContentSha256)
            {
                if (before.Matches(original))
                    throw new IOException("File content changed without a distinguishable fingerprint; timestamp recovery requires review.");
                await _syncStateStore.CompleteTimestampRepairAsync(repair, null, cancellationToken);
                return null;
            }
            if (!TryGetFingerprint(path, out var checkedFingerprint) || checkedFingerprint != before)
                throw new IOException("The local file changed while timestamp correction was being prepared.");

            DownloadedFileTimestamps.Apply(path, desired);
            if (!TryGetFingerprint(path, out var after) || after.FileSize != before.FileSize
                || await HashFileAsync(path, cancellationToken) != repair.ContentSha256)
            {
                throw new IOException("The local file changed during timestamp correction; keeping its recovery journal.");
            }

            // Persist the filesystem's actual precision. This changes neither
            // transfer history nor the successful-sync high-water timestamp.
            var updated = original with { LastWriteTimeUtc = new DateTimeOffset(after.LastWriteTimeUtcTicks, TimeSpan.Zero) };
            await _syncStateStore.CompleteTimestampRepairAsync(repair, updated, cancellationToken);
            _stateByPath[path] = updated;
            if (_pollingBaseline.TryGetValue(context.NormalizedRoot, out var baseline)) baseline[path] = after;
            _logger.LogInformation("Restored original timestamps for synchronized file {FilePath}.", path);
            return updated;
        }
        finally
        {
            _downloadsInProgress.TryRemove(path, out _);
        }
    }

    private static async Task<string> HashFileAsync(string path, CancellationToken cancellationToken)
    {
        await using var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
            81920, FileOptions.Asynchronous | FileOptions.SequentialScan);
        return Convert.ToHexString(await SHA256.HashDataAsync(file, cancellationToken));
    }

    private static bool TimestampsMatch(string path, DownloadedFileTimestampValues desired) =>
        TimestampMatches(File.GetLastWriteTimeUtc(path).Ticks, desired.LastWriteTimeUtc)
        && (!OperatingSystem.IsWindows()
            || TimestampMatches(File.GetCreationTimeUtc(path).Ticks, desired.CreationTimeUtc));

    private static bool TimestampMatches(long actualTicks, DateTimeOffset desired)
    {
        // FAT can truncate modification times to two-second boundaries.
        var difference = desired.UtcTicks - actualTicks;
        return difference >= 0 && difference < TimeSpan.TicksPerSecond * 2;
    }

    private sealed class TimestampRepairException(Exception inner)
        : Exception("A pending timestamp correction requires recovery before synchronization can continue.", inner);
}
