using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IFileReadinessChecker
{
    Task<bool> WaitUntilReadyAsync(string filePath, TimeSpan timeout, CancellationToken cancellationToken);

    Task<bool> WaitUntilReadyAsync(SecureWatchRoot root, string relativePath, TimeSpan timeout, CancellationToken cancellationToken) =>
        new FileReadinessChecker().WaitUntilReadyAsync(root, relativePath, timeout, cancellationToken);
}
