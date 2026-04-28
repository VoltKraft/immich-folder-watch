using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class StubAutoStartManager : IAutoStartManager
{
    public Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default)
        => Task.FromResult(false);

    public Task EnableAsync(CancellationToken cancellationToken = default)
        => Task.CompletedTask;

    public Task DisableAsync(CancellationToken cancellationToken = default)
        => Task.CompletedTask;
}
