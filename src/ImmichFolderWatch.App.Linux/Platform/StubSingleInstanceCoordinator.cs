using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class StubSingleInstanceCoordinator : ISingleInstanceCoordinator
{
    public bool IsPrimaryInstance => true;

    public void StartListening(Action onShowGuiRequested)
    {
    }

    public bool TrySignalShowGui(TimeSpan timeout) => false;

    public void Dispose()
    {
    }
}
