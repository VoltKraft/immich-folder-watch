using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Interfaces;

/// <summary>
/// Checks whether a newer application release is available.
/// </summary>
public interface IUpdateChecker
{
    /// <summary>
    /// Returns a newer release, or <see langword="null"/> when the installed version is current
    /// or the best-effort check cannot be completed.
    /// </summary>
    /// <param name="currentVersion">The installed three-component application version.</param>
    /// <param name="cancellationToken">Cancels the check during application shutdown.</param>
    /// <exception cref="OperationCanceledException">The caller cancels <paramref name="cancellationToken"/>.</exception>
    Task<UpdateInfo?> CheckAsync(Version currentVersion, CancellationToken cancellationToken);
}
