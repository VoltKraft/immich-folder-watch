namespace ImmichFolderWatch.Core.Interfaces;

public interface IImmichRealtimeClient : IAsyncDisposable
{
    event EventHandler? RemoteChangeDetected;

    Task StartAsync(CancellationToken cancellationToken);

    Task StopAsync(CancellationToken cancellationToken);
}
