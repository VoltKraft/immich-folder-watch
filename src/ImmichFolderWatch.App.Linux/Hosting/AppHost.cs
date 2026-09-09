using System.Net;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Linux.Logging;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.App.Linux.Hosting;

/// <summary>
/// Linux-side wrapper around Microsoft.Extensions.Hosting that starts +
/// stops + restarts the FolderWatchWorker / ServerConnectionMonitor
/// pipeline against an AppConfig. Mirrors the WPF AppHost but routes
/// logs to journald or to the FileLoggerProvider depending on
/// config.Logging.Target — coerced through IPlatformLoggingCapabilities
/// so a stale target=eventLog (saved by the WPF head) becomes journald.
/// </summary>
public sealed class AppHost : IAsyncDisposable
{
    private readonly SyncStatusProvider _syncStatusProvider;
    private readonly IPlatformPaths _platformPaths;
    private readonly IPlatformLoggingCapabilities _loggingCapabilities;
    private readonly SessionLogBuffer _sessionLogs;
    private readonly Func<AppConfig, IHost> _hostFactory;
    private readonly SemaphoreSlim _lifecycleGate = new(1, 1);
    private IHost? _host;
    private AppConfig? _currentConfig;

    public AppHost(
        SyncStatusProvider syncStatusProvider,
        IPlatformPaths platformPaths,
        IPlatformLoggingCapabilities loggingCapabilities,
        SessionLogBuffer sessionLogs)
        : this(syncStatusProvider, platformPaths, loggingCapabilities, sessionLogs, null)
    {
    }

    // Allows lifecycle tests to control asynchronous start/stop without real workers or Immich.
    internal AppHost(
        SyncStatusProvider syncStatusProvider,
        IPlatformPaths platformPaths,
        IPlatformLoggingCapabilities loggingCapabilities,
        SessionLogBuffer sessionLogs,
        Func<AppConfig, IHost>? hostFactory)
    {
        ArgumentNullException.ThrowIfNull(syncStatusProvider);
        ArgumentNullException.ThrowIfNull(platformPaths);
        ArgumentNullException.ThrowIfNull(loggingCapabilities);
        _syncStatusProvider = syncStatusProvider;
        _platformPaths = platformPaths;
        _loggingCapabilities = loggingCapabilities;
        _sessionLogs = sessionLogs;
        _hostFactory = hostFactory ?? BuildHost;
    }

    public AppConfig? CurrentConfig => _currentConfig;

    public string? LastLoggingWarning { get; private set; }

    public bool IsRunning => _host is not null;

    public async Task StartAsync(AppConfig config, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(config);

        await _lifecycleGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_host is not null)
            {
                return;
            }

            await StartInternalAsync(config, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _lifecycleGate.Release();
        }
    }

    public async Task StopAsync(CancellationToken cancellationToken = default)
    {
        await _lifecycleGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            await StopInternalAsync(cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _lifecycleGate.Release();
        }
    }

    public async Task RestartAsync(AppConfig newConfig, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(newConfig);

        await _lifecycleGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            await StopInternalAsync(cancellationToken).ConfigureAwait(false);
            await StartInternalAsync(newConfig, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _lifecycleGate.Release();
        }
    }

    private async Task StartInternalAsync(AppConfig config, CancellationToken cancellationToken)
    {
        var errors = AppConfigValidator.Validate(config);
        if (errors.Count > 0)
        {
            throw new InvalidOperationException(string.Join(Environment.NewLine, errors));
        }
        var host = _hostFactory(config);
        try
        {
            await host.StartAsync(cancellationToken).ConfigureAwait(false);
        }
        catch
        {
            host.Dispose();
            throw;
        }
        _host = host;
        _currentConfig = config;
        if (LastLoggingWarning is not null)
        {
            host.Services.GetRequiredService<ILogger<AppHost>>().LogWarning("{Warning}", LastLoggingWarning);
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
            await _host.StopAsync(cancellationToken).ConfigureAwait(false);
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
            ProductVersionProvider.GetProductVersion(typeof(AppHost).Assembly)?.ToString(3) ?? "0.0.0";

        var builder = Host.CreateApplicationBuilder();

        builder.Logging.ClearProviders();
        builder.Logging.SetMinimumLevel(logLevel);
        builder.Logging.AddProvider(new SessionLoggerProvider(_sessionLogs));
        LastLoggingWarning = null;

        var effectiveTarget = _loggingCapabilities.CoerceToSupported(config.Logging.Target);
        if (LogTargets.IsJournald(effectiveTarget))
        {
            builder.Logging.AddSystemdConsole(options =>
            {
                options.IncludeScopes = false;
                options.UseUtcTimestamp = true;
            });
        }
        else
        {
            // target=File: SimpleConsole for dev visibility + FileLoggerProvider
            // against config.Logging.LogDirectory (defaulting to
            // IPlatformPaths.GetLogDirectory when unset, so the Open Logs
            // button always resolves to a real directory).
            builder.Logging.AddSimpleConsole(options =>
            {
                options.TimestampFormat = "yyyy-MM-dd HH:mm:ss.fff ";
                options.SingleLine = true;
            });

            var logDirectory = !string.IsNullOrWhiteSpace(config.Logging.LogDirectory)
                ? config.Logging.LogDirectory
                : _platformPaths.GetLogDirectory();
            try
            {
                Directory.CreateDirectory(logDirectory);
                builder.Logging.AddProvider(new FileLoggerProvider(logDirectory, logLevel));
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                LastLoggingWarning = $"File logging is unavailable: {ex.Message}";
            }
        }

        // Keep other hosted services available after a worker failure, such as
        // an inaccessible document-portal mount. The user can inspect the log,
        // renew the folder grant and restart the worker through Save & Apply.
        builder.Services.Configure<HostOptions>(options =>
        {
            options.BackgroundServiceExceptionBehavior = BackgroundServiceExceptionBehavior.Ignore;
        });

        builder.Services.AddSingleton(config);
        builder.Services.AddSingleton(config.Retry);
        builder.Services.AddSingleton(_syncStatusProvider);
        builder.Services.AddSingleton<IPlatformPaths>(_platformPaths);
        builder.Services.AddSingleton<IFileReadinessChecker, FileReadinessChecker>();
        builder.Services.AddSingleton<ILocalFileDeletionService, LocalFileDeletionService>();
        builder.Services.AddSingleton<IUploadBatchQueue, UploadBatchQueue>();
        builder.Services.AddSingleton<ISyncStateStore, SqliteSyncStateStore>();

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
        await _lifecycleGate.WaitAsync().ConfigureAwait(false);
        try
        {
            await StopInternalAsync(CancellationToken.None).ConfigureAwait(false);
        }
        finally
        {
            _lifecycleGate.Release();
        }

        _lifecycleGate.Dispose();
    }
}
