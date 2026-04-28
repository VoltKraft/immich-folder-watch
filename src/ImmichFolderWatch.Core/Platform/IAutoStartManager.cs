namespace ImmichFolderWatch.Core.Platform;

public interface IAutoStartManager
{
    Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default);

    Task EnableAsync(CancellationToken cancellationToken = default);

    Task DisableAsync(CancellationToken cancellationToken = default);
}
