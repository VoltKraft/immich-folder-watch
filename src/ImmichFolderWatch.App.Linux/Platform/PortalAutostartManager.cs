using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.App.Linux.Platform;

/// <summary>Persists only portal-confirmed autostart state and serializes background permission changes.</summary>
public sealed class PortalAutostartManager(IBackgroundPortalRequest portal, IPlatformPaths paths,
    ILogger<PortalAutostartManager>? logger = null) : IAutoStartManager
{
    private const string AutostartFlagFileName = "autostart-requested";
    private const string InitializedFlagFileName = "autostart-initialized";
    private readonly SemaphoreSlim _gate = new(1, 1);

    /// <summary>
    /// Offers autostart once for a new installation. Existing configurations and
    /// remembered choices are preserved; a denied request can be retried in settings.
    /// </summary>
    public async Task InitializeAsync(bool configurationExists, CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var initializedPath = Path.Combine(paths.GetUserDataRoot(), InitializedFlagFileName);
            if (configurationExists || File.Exists(initializedPath) || File.Exists(GetFlagPath()))
            {
                return;
            }

            Directory.CreateDirectory(paths.GetUserDataRoot());
            File.WriteAllText(initializedPath, DateTime.UtcNow.ToString("O"));
            await SetEnabledCoreAsync(true, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex)
        {
            (logger ?? NullLogger<PortalAutostartManager>.Instance).LogWarning(ex,
                "Initial autostart request failed; autostart can be changed in settings.");
        }
        finally
        {
            _gate.Release();
        }
    }

    /// <summary>Returns the last confirmed state; the portal does not provide a query for external changes.</summary>
    public Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(File.Exists(GetFlagPath()));
    }

    public Task EnableAsync(CancellationToken cancellationToken = default)
        => SetEnabledAsync(true, cancellationToken);

    public Task DisableAsync(CancellationToken cancellationToken = default)
        => SetEnabledAsync(false, cancellationToken);

    /// <summary>Requests background permission without changing the last confirmed autostart choice.</summary>
    public async Task<bool> RequestBackgroundPermissionAsync(CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var autostart = await IsEnabledAsync(cancellationToken).ConfigureAwait(false);
            var result = await portal.RequestAsync(autostart, cancellationToken).ConfigureAwait(false);
            EnsureCompleted(result);
            PersistState(result.Autostart);
            return result.Background;
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task SetEnabledAsync(bool enabled, CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            await SetEnabledCoreAsync(enabled, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task SetEnabledCoreAsync(bool enabled, CancellationToken cancellationToken)
    {
        var result = await portal.RequestAsync(enabled, cancellationToken).ConfigureAwait(false);
        EnsureCompleted(result);
        // Even a successful interaction can decline autostart. Persist the actual
        // result first so a later close-to-background request cannot re-enable it.
        PersistState(result.Autostart);
        if (result.Autostart != enabled)
        {
            throw new InvalidOperationException("The Background portal did not grant the requested autostart setting.");
        }
    }

    private static void EnsureCompleted(BackgroundPortalResponse result)
    {
        if (result.ResponseCode == 1)
        {
            throw new OperationCanceledException("The Background portal request was cancelled by the user.");
        }
        if (result.ResponseCode != 0)
        {
            throw new InvalidOperationException("The Background portal request was denied or failed.");
        }
    }

    private void PersistState(bool enabled)
    {
        if (enabled)
        {
            Directory.CreateDirectory(paths.GetUserDataRoot());
            File.WriteAllText(GetFlagPath(), DateTime.UtcNow.ToString("O"));
        }
        else if (File.Exists(GetFlagPath()))
        {
            File.Delete(GetFlagPath());
        }
    }

    private string GetFlagPath() => Path.Combine(paths.GetUserDataRoot(), AutostartFlagFileName);
}
