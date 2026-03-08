namespace ImmichFolderWatch.Core.Interfaces;

public interface IImmichConnectivityVerifier
{
    Task PingAsync(CancellationToken cancellationToken);
}
