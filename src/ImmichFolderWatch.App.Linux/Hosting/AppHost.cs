using System.Net;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.App.Linux.Hosting;

/// <summary>
/// Linux-side wrapper around Microsoft.Extensions.Hosting that starts +
/// stops + restarts the FolderWatchWorker / ServerConnectionMonitor
/// pipeline against an AppConfig. Mirrors the WPF AppHost but skips the
/// Windows EventLog target — the Linux head logs to journald (when
/// FLATPAK_ID/INVOCATION_ID is detected) or to the file logger,
/// configured by the FileLoggerProvider against config.Logging.LogDirectory.
/// </summary>
public sealed class AppHost : IAsyncDisposable
{
    private readonly SyncStatusProvider _syncStatusProvider;
    private readonly SemaphoreSlim _lifecycleGate = new(1, 1);
    private IHost? _host;
    private AppConfig? _currentConfig;

    public AppHost(SyncStatusProvider syncStatusProvider)
    {
        ArgumentNullException.ThrowIfNull(syncStatusProvider);
        _syncStatusProvider = syncStatusProvider;
    }

    public AppConfig? CurrentConfig => _currentConfig;

    public bool IsRunning => _host is not null;

    public async Task StartAsync(AppConfig config, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(config);

        await _lifecycleGate.WaitAsync(cancellationToken);
        try
        {
            if (_host is not null)
            {
                return;
            }

            _host = BuildHost(config);
            _currentConfig = config;
            await _host.StartAsync(cancellationToken);
        }
        finally
        {
            _lifecycleGate.Release();
        }
    }

    public async Task StopAsync(CancellationToken cancellationToken = default)
    {
        await _lifecycleGate.WaitAsync(cancellationToken);
        try
        {
            await StopInternalAsync(cancellationToken);
        }
        finally
        {
            _lifecycleGate.Release();
        }
    }

    public async Task RestartAsync(AppConfig newConfig, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(newConfig);

        await _lifecycleGate.WaitAsync(cancellationToken);
        try
        {
            await StopInternalAsync(cancellationToken);
            _host = BuildHost(newConfig);
            _currentConfig = newConfig;
            await _host.StartAsync(cancellationToken);
        }
        finally
        {
            _lifecycleGate.Release();
        }
    }

    private async Task StopInternalAsync(CancellationToken cancellationToken)
    {
        if (_host is null)
        {
            return;
        }

        try
        {
            await _host.StopAsync(cancellationToken);
        }
        catch (Exception)
        {
            // Best-effort shutdown; let the dispose path clean up the rest.
        }

        _host.Dispose();
        _host = null;
        _syncStatusProvider.ReportBatchCompleted();
        _syncStatusProvider.ReportPendingCount(0);
    }

    private IHost BuildHost(AppConfig config)
    {
        var logLevel = LogLevelParser.Parse(config.Logging.Level);
        var productVersion =
            typeof(AppHost).Assembly.GetName().Version?.ToString(3) ?? "0.0.0";

        var builder = Host.CreateApplicationBuilder();

        builder.Logging.ClearProviders();
        builder.Logging.SetMinimumLevel(logLevel);

        if (JournaldLoggingExtensions.IsJournaldDetected())
        {
            builder.Logging.AddSystemdConsole(options =>
            {
                options.IncludeScopes = false;
                options.UseUtcTimestamp = true;
            });
        }
        else
        {
            builder.Logging.AddSimpleConsole(options =>
            {
                options.TimestampFormat = "yyyy-MM-dd HH:mm:ss.fff ";
                options.SingleLine = true;
            });
        }

        if (LogTargets.IsFile(config.Logging.Target)
            && !string.IsNullOrWhiteSpace(config.Logging.LogDirectory))
        {
            Directory.CreateDirectory(config.Logging.LogDirectory);
            builder.Logging.AddProvider(
                new FileLoggerProvider(config.Logging.LogDirectory, logLevel));
        }

        builder.Services.AddSingleton(config);
        builder.Services.AddSingleton(config.Retry);
        builder.Services.AddSingleton(_syncStatusProvider);
        builder.Services.AddSingleton<IFileReadinessChecker, FileReadinessChecker>();
        builder.Services.AddSingleton<IUploadBatchQueue, UploadBatchQueue>();

        var normalizedApiUrl = AppConfigValidator.EnsureTrailingSlash(config.Immich.ServerApiUrl);

        builder.Services.AddSingleton<SocketsHttpHandler>(_ => new SocketsHttpHandler
        {
            PooledConnectionLifetime = TimeSpan.FromMinutes(10),
            AutomaticDecompression = DecompressionMethods.All,
        });

        builder.Services.AddSingleton(sp =>
        {
            var handler = sp.GetRequiredService<SocketsHttpHandler>();
            var client = new HttpClient(handler, disposeHandler: false)
            {
                BaseAddress = new Uri(normalizedApiUrl, UriKind.Absolute),
                Timeout = TimeSpan.FromMinutes(2),
            };
            client.DefaultRequestHeaders.Add("x-api-key", config.Immich.ApiKey);
            client.DefaultRequestHeaders.UserAgent.ParseAdd($"immich-folder-watch/{productVersion}");
            return client;
        });

        builder.Services.AddSingleton<IImmichAssetClient, ImmichAssetClient>();
        builder.Services.AddSingleton<IImmichRealtimeClient, ImmichRealtimeClient>();

        builder.Services.AddHostedService<FolderWatchWorker>();
        builder.Services.AddHostedService<ServerConnectionMonitor>();

        return builder.Build();
    }

    public async ValueTask DisposeAsync()
    {
        await _lifecycleGate.WaitAsync();
        try
        {
            await StopInternalAsync(CancellationToken.None);
        }
        finally
        {
            _lifecycleGate.Release();
        }

        _lifecycleGate.Dispose();
    }
}
