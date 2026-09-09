using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.App.Linux.Platform;

/// <summary>Requests shell permission when the window is hidden, preserving the user's autostart choice.</summary>
public sealed class BackgroundPortalClient(PortalAutostartManager autostartManager, ILogger<BackgroundPortalClient> logger)
{
    private int _requested;

    /// <summary>
    /// Requests once per process. Observes the portal response and logs denial or failure;
    /// the application's explicit Quit action remains responsible for stopping its worker.
    /// </summary>
    public async Task RequestBackgroundAsync(CancellationToken cancellationToken = default)
    {
        if (Interlocked.CompareExchange(ref _requested, 1, 0) == 1)
        {
            return;
        }

        try
        {
            if (await autostartManager.RequestBackgroundPermissionAsync(cancellationToken).ConfigureAwait(false))
            {
                logger.LogInformation("Background portal: background permission granted.");
            }
            else
            {
                logger.LogWarning("Background portal: background permission was not granted.");
            }
        }
        catch (Exception ex)
        {
            logger.LogDebug(ex, "Background portal request failed; continuing without portal-based shell presence.");
        }
    }
}
