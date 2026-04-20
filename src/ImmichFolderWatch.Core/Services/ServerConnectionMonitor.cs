using ImmichFolderWatch.Core.Interfaces;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Core.Services;

public sealed class ServerConnectionMonitor : BackgroundService
{
    private static readonly TimeSpan CheckInterval = TimeSpan.FromSeconds(30);

    private readonly IImmichAssetClient _immichAssetClient;
    private readonly SyncStatusProvider _syncStatusProvider;
    private readonly ILogger<ServerConnectionMonitor> _logger;

    public ServerConnectionMonitor(
        IImmichAssetClient immichAssetClient,
        SyncStatusProvider syncStatusProvider,
        ILogger<ServerConnectionMonitor> logger)
    {
        _immichAssetClient = immichAssetClient;
        _syncStatusProvider = syncStatusProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(CheckInterval);

        do
        {
            await CheckOnceAsync(stoppingToken);
        }
        while (await SafeWaitAsync(timer, stoppingToken));
    }

    private async Task CheckOnceAsync(CancellationToken cancellationToken)
    {
        _syncStatusProvider.ReportServerChecking();

        try
        {
            await _immichAssetClient.PingAsync(cancellationToken);
            _syncStatusProvider.ReportServerReachable(true);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Immich server ping failed.");
            _syncStatusProvider.ReportServerReachable(false, ex.Message);
        }
    }

    private static async Task<bool> SafeWaitAsync(PeriodicTimer timer, CancellationToken cancellationToken)
    {
        try
        {
            return await timer.WaitForNextTickAsync(cancellationToken);
        }
        catch (OperationCanceledException)
        {
            return false;
        }
    }
}
