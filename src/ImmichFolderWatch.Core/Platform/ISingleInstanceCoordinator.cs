namespace ImmichFolderWatch.Core.Platform;

public interface ISingleInstanceCoordinator : IDisposable
{
    bool IsPrimaryInstance { get; }

    void StartListening(Action onShowGuiRequested);

    bool TrySignalShowGui(TimeSpan timeout);
}
