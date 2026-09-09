using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using ImmichFolderWatch.App.Linux.Hosting;
using ImmichFolderWatch.App.Linux.Logging;
using ImmichFolderWatch.App.Linux.Platform;
using ImmichFolderWatch.App.Linux.ViewModels;
using ImmichFolderWatch.App.Linux.Views;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.App.Linux;

public sealed partial class App : Application
{
    private readonly CancellationTokenSource _shutdown = new();
    private MainWindow? _mainWindow;
    private AvaloniaTrayHost? _trayHost;
    private Task? _updateCheckTask;
    private Task? _shutdownTask;
    private Task? _disposeTask;
    private ServiceProvider? _provider;

    public static CancellationToken ShutdownToken => (Current as App)?._shutdown.Token ?? CancellationToken.None;

    /// <summary>
    /// Service-locator handle for code-behind click handlers in
    /// <see cref="MainWindow"/>. Avalonia's XAML loader requires a
    /// parameterless ctor on Window subclasses, so DI cannot inject
    /// dependencies through the View ctor; the handlers reach into
    /// this provider instead.
    /// </summary>
    public static IServiceProvider? Services { get; private set; }

    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            // Mirror the WPF App.xaml's ShutdownMode="OnExplicitShutdown".
            // Closing the main window then no longer terminates the
            // process; explicit Quit paths (footer button, tray context
            // menu where enabled, second-instance handoff) call
            // desktop.Shutdown(0) themselves.
            desktop.ShutdownMode = ShutdownMode.OnExplicitShutdown;

            // PortalAutostartManager hands the Background portal a
            // commandline of ["immich-folder-watch", "--background"];
            // that is the autostart entry GNOME executes after login.
            // Detect the flag here (and accept --autostart for parity
            // with the WPF AutostartManager.AutostartArgument) so we
            // know to skip the implicit MainWindow.Show() when a tray
            // entry point is available.
            var startHidden = (desktop.Args ?? Array.Empty<string>()).Any(a =>
                string.Equals(a, "--background", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(a, "--autostart", StringComparison.OrdinalIgnoreCase));

            // Observe unexpected background failures and retain their diagnostic
            // details even when a third-party asynchronous operation is abandoned.
            TaskScheduler.UnobservedTaskException += static (sender, args) =>
            {
                Console.Error.WriteLine($"[unobserved-task] {args.Exception}");
                args.SetObserved();
            };

            var services = new ServiceCollection();
            var sessionLogs = new SessionLogBuffer();
            services.AddSingleton(sessionLogs);
            services.AddLogging(builder =>
            {
                builder.SetMinimumLevel(LogLevel.Information);
                builder.AddProvider(new SessionLoggerProvider(sessionLogs));
                if (JournaldLoggingExtensions.IsJournaldDetected())
                {
                    // systemd / journald style for autostart + Flatpak launches
                    // (one provider only — stacking SimpleConsole + Systemd
                    // collides on the FormatterName, last one wins).
                    builder.AddSystemdConsole(options =>
                    {
                        options.IncludeScopes = false;
                        options.UseUtcTimestamp = true;
                    });
                }
                else
                {
                    builder.AddSimpleConsole(options =>
                    {
                        options.SingleLine = true;
                        options.IncludeScopes = false;
                        options.TimestampFormat = "HH:mm:ss ";
                    });
                }
            });
            services.AddSingleton<DBusSession>();
            services.AddSingleton<IPlatformPaths, XdgPlatformPaths>();
            services.AddSingleton<IBackgroundPortalRequest, DBusBackgroundPortalRequest>();
            services.AddSingleton<PortalAutostartManager>();
            services.AddSingleton<IAutoStartManager>(sp => sp.GetRequiredService<PortalAutostartManager>());
            services.AddSingleton<IThemeProvider, PortalThemeProvider>();
            services.AddSingleton<INotifier, DBusNotifier>();
            services.AddSingleton<ISingleInstanceCoordinator, UnixSingleInstanceCoordinator>();
            services.AddSingleton<IUiDispatcher, AvaloniaUiDispatcher>();
            services.AddSingleton<IPlatformLoggingCapabilities, LinuxLoggingCapabilities>();
            services.AddSingleton<AvaloniaTrayHost>();
            services.AddSingleton<PortalFolderPicker>(sp =>
                new PortalFolderPicker(
                    () => _mainWindow,
                    sp.GetRequiredService<ILogger<PortalFolderPicker>>()));
            services.AddSingleton<DocumentPortalClient>();
            services.AddSingleton<BackgroundPortalClient>();
            services.AddSingleton(LocalizationService.Instance);
            services.AddSingleton<LocalizationProxy>(sp =>
                new LocalizationProxy(
                    sp.GetRequiredService<LocalizationService>(),
                    sp.GetRequiredService<IUiDispatcher>()));
            services.AddSingleton<SyncStatusProvider>();
            services.AddSingleton<IAppConfigLoader, AppConfigLoader>();
            services.AddSingleton<AppConfigLoader>();
            services.AddSingleton<AppHost>();
            services.AddSingleton<ConfigVerificationRunner>();
            services.AddSingleton(_ => new ConfigApplyService());
            services.AddSingleton(_ => new HttpClient(new HttpClientHandler
            {
                AllowAutoRedirect = false,
            })
            {
                Timeout = TimeSpan.FromSeconds(5),
            });
            services.AddSingleton<IUpdateChecker, GitHubUpdateChecker>();
            services.AddSingleton<MainWindowViewModel>();
            services.AddSingleton<ShellViewModel>();
            var provider = services.BuildServiceProvider();
            Services = provider;
            _provider = provider;

            var single = provider.GetRequiredService<ISingleInstanceCoordinator>();
            if (!single.IsPrimaryInstance)
            {
                single.TrySignalShowGui(TimeSpan.FromSeconds(2));
                // Defer Shutdown until the dispatcher loop is running. Calling
                // it directly here races with StartCore→MainLoop→PushFrame and
                // surfaces as "Cannot perform requested operation because the
                // Dispatcher shut down" in the second instance. Queuing it via
                // UIThread.Post lets the main loop spin up first and then
                // process the shutdown gracefully.
                Avalonia.Threading.Dispatcher.UIThread.Post(() => _ = ShutdownAsync());
                return;
            }

            // The Avalonia MainWindow expects MainWindowViewModel as its
            // DataContext (mirrors the WPF head); the LocalizationProxy is
            // resolved here purely for its side-effect of subscribing to
            // LocalizationService.LanguageChanged so the {StaticResource Loc}
            // bindings refresh when the language switches.
            _ = provider.GetRequiredService<LocalizationProxy>();
            ApplyStartupLanguage(provider);
            var viewModel = provider.GetRequiredService<MainWindowViewModel>();
            var productVersion = ProductVersionProvider.GetProductVersion(typeof(App).Assembly);
            viewModel.ProductVersionText = $"Version {productVersion?.ToString(3) ?? "unknown"}";
            _updateCheckTask = CheckForUpdatesAsync(provider, viewModel, productVersion, _shutdown.Token);
            _mainWindow = new MainWindow
            {
                DataContext = viewModel,
            };

            single.StartListening(() => Avalonia.Threading.Dispatcher.UIThread.Post(() =>
            {
                _mainWindow?.Show();
                _mainWindow?.Activate();
            }));

            var theme = provider.GetRequiredService<IThemeProvider>();
            theme.Initialize();

            _trayHost = provider.GetRequiredService<AvaloniaTrayHost>();
            _trayHost.OpenRequested += (_, _) => Avalonia.Threading.Dispatcher.UIThread.Post(() =>
            {
                _mainWindow?.Show();
                _mainWindow?.Activate();
            });
            _trayHost.RestartRequested += (_, _) => _ = RestartSyncAsync();
            _trayHost.QuitRequested += (_, _) => _ = ShutdownAsync();
            _trayHost.TrayAvailable += (_, _) => viewModel.TrayStatusMessage = string.Empty;
            _trayHost.TrayUnavailable += (_, _) => Avalonia.Threading.Dispatcher.UIThread.Post(() =>
            {
                viewModel.TrayStatusMessage = ImmichFolderWatch.App.Shared.Resources.Strings.Tray_Unavailable;
                // A missing or disappearing tray must never strand an autostarted
                // process without a visible way to reach the configuration window.
                if (_mainWindow is { IsVisible: false })
                {
                    _mainWindow.Show();
                    _mainWindow.Activate();
                }
            });
            _ = _trayHost.StartAsync(this, _shutdown.Token);

            // Start() automatically shows desktop.MainWindow. A background launch
            // bootstraps directly; failed tray registration shows the window above.
            var shouldStartHidden = startHidden;
            if (!shouldStartHidden)
            {
                desktop.MainWindow = _mainWindow;
            }
            else
            {
                // Window stays hidden, so MainWindow.Opened never fires —
                // and OnOpened is what normally loads the config + starts
                // AppHost (FolderWatchWorker, ServerConnectionMonitor,
                // ImmichRealtimeClient). Bootstrap directly here so the
                // background watcher actually runs without a visible UI.
                _ = _mainWindow.EnsureBootstrappedAsync();
            }
            void RefreshTrayMessage(object? sender, EventArgs args)
            {
                viewModel.TrayStatusMessage = _trayHost is { IsTrayIconRegistered: true }
                    ? string.Empty
                    : ImmichFolderWatch.App.Shared.Resources.Strings.Tray_Unavailable;
            }
            LocalizationService.Instance.LanguageChanged += RefreshTrayMessage;
            desktop.ShutdownRequested += (_, _) =>
            {
                // The desktop callback is synchronous. Do not veto logout; stop
                // services off the UI thread before allowing windows to close.
                _shutdown.Cancel();
                if (_mainWindow is not null) _mainWindow.IsExiting = true;
                DisposeServicesAsync().GetAwaiter().GetResult();
            };
            desktop.Exit += (_, _) =>
            {
                LocalizationService.Instance.LanguageChanged -= RefreshTrayMessage;
                _shutdown.Cancel();
                _trayHost?.Dispose();
            };
        }

        base.OnFrameworkInitializationCompleted();
    }

    /// <summary>Stops synchronization before ending the desktop lifetime. Repeated quit requests share one task.</summary>
    public Task ShutdownAsync() => _shutdownTask ??= ShutdownCoreAsync();

    private async Task ShutdownCoreAsync()
    {
        _shutdown.Cancel();
        if (_mainWindow is not null)
        {
            _mainWindow.IsExiting = true;
        }
        try
        {
            await Task.WhenAll(_mainWindow?.WaitForBootstrapAsync() ?? Task.CompletedTask,
                _updateCheckTask ?? Task.CompletedTask);
        }
        catch (OperationCanceledException) when (_shutdown.IsCancellationRequested)
        {
        }
        catch (Exception ex)
        {
            _provider?.GetRequiredService<ILogger<App>>().LogWarning(ex, "A startup task failed during shutdown.");
        }

        await DisposeServicesAsync();
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.Shutdown(0);
        }
    }

    private Task DisposeServicesAsync()
    {
        if (_disposeTask is not null) return _disposeTask;
        _trayHost?.Dispose();
        var provider = _provider;
        _provider = null;
        Services = null;
        return _disposeTask = Task.Run(async () =>
        {
            try
            {
                if (provider is not null) await provider.DisposeAsync();
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"Shutdown cleanup failed: {ex}");
            }
        });
    }

    private async Task RestartSyncAsync()
    {
        if (_provider is null || _shutdown.IsCancellationRequested)
        {
            return;
        }
        try
        {
            var paths = _provider.GetRequiredService<IPlatformPaths>();
            var config = _provider.GetRequiredService<AppConfigLoader>().Load(paths.GetConfigPath());
            await _provider.GetRequiredService<AppHost>().RestartAsync(config, _shutdown.Token);
        }
        catch (OperationCanceledException) when (_shutdown.IsCancellationRequested)
        {
        }
        catch (Exception ex)
        {
            _provider?.GetRequiredService<ILogger<App>>().LogWarning(ex, "Could not restart synchronization.");
            if (_mainWindow?.DataContext is MainWindowViewModel vm)
            {
                vm.OperationMessage = ex.Message;
            }
        }
    }

    private static void ApplyStartupLanguage(IServiceProvider services)
    {
        var language = LocalizationService.LanguageAuto;
        try
        {
            var path = services.GetRequiredService<IPlatformPaths>().GetConfigPath();
            if (File.Exists(path))
            {
                language = services.GetRequiredService<AppConfigLoader>().LoadForEditing(path).Localization.Language;
            }
        }
        catch (Exception ex)
        {
            services.GetRequiredService<ILogger<App>>().LogWarning(ex, "Could not read the startup language.");
        }
        LocalizationService.Instance.SetLanguage(language);
    }

    private static async Task CheckForUpdatesAsync(
        IServiceProvider services,
        MainWindowViewModel viewModel,
        Version? productVersion,
        CancellationToken cancellationToken)
    {
        var logger = services.GetRequiredService<ILogger<App>>();
        if (productVersion is null)
        {
            logger.LogWarning("The installed product version could not be determined; skipping the update check.");
            return;
        }

        try
        {
            var updateInfo = await services
                .GetRequiredService<IUpdateChecker>()
                .CheckAsync(productVersion, cancellationToken)
                .ConfigureAwait(false);
            viewModel.ApplyUpdateInfo(updateInfo);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "The update check failed and will be ignored.");
        }
    }
}
