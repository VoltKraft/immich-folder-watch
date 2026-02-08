namespace ImmichFolderWatch.Core.Interfaces;

public interface IFileReadinessChecker
{
    Task<bool> WaitUntilReadyAsync(string filePath, TimeSpan timeout, CancellationToken cancellationToken);
}
