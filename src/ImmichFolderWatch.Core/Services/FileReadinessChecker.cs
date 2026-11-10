using ImmichFolderWatch.Core.Interfaces;

namespace ImmichFolderWatch.Core.Services;

public sealed class FileReadinessChecker : IFileReadinessChecker
{
    private static readonly TimeSpan DefaultPollInterval = TimeSpan.FromMilliseconds(250);

    public async Task<bool> WaitUntilReadyAsync(string filePath, TimeSpan timeout, CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(filePath);
        var fullPath = Path.GetFullPath(filePath);
        using var root = SecureWatchRoot.Open(Path.GetDirectoryName(fullPath)!);
        return await WaitUntilReadyAsync(root, Path.GetFileName(fullPath), timeout, cancellationToken);
    }

    public async Task<bool> WaitUntilReadyAsync(SecureWatchRoot root, string relativePath, TimeSpan timeout, CancellationToken cancellationToken)
    {
        if (timeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(timeout), "Timeout must be greater than zero.");
        }

        var deadline = DateTime.UtcNow.Add(timeout);

        while (DateTime.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();

            try
            {
                if (!root.FileExists(relativePath)) return false;
                using var file = root.OpenRead(relativePath);
                var stream = file.Stream;
                _ = stream.Length;
                return true;
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }

            var remaining = deadline - DateTime.UtcNow;
            if (remaining <= TimeSpan.Zero)
            {
                break;
            }

            var delay = remaining < DefaultPollInterval ? remaining : DefaultPollInterval;
            await Task.Delay(delay, cancellationToken);
        }

        return false;
    }
}
