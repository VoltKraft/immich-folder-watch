using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using ImmichFolderWatch.App.Linux.Hosting;
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
    private MainWindow? _mainWindow;
    private AvaloniaTrayHost? _trayHost;

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
            // process — MainWindow.OnClosing decides hide-vs-exit based
            // on whether a tray icon is registered, and explicit Quit
            // paths (footer button, tray context menu in 3.8.D, second
            // instance handoff) call desktop.Shutdown(0) themselves.
            desktop.ShutdownMode = ShutdownMode.OnExplicitShutdown;

            // PortalAutostartManager hands the Background portal a
            // commandline of ["immich-folder-watch", "--background"];
            // that is the autostart entry GNOME executes after login.
            // Detect the flag here (and accept --autostart for parity
            // with the WPF AutostartManager.AutostartArgument) so we
            // know to skip the implicit MainWindow.Show() and let the
            // user discover the running app via the tray icon /
            // Background Apps panel instead of having a window pop up
            // in their face on every login.
            var startHidden = (desktop.Args ?? Array.Empty<string>()).Any(a =>
                string.Equals(a, "--background", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(a, "--autostart", StringComparison.OrdinalIgnoreCase));

            // Avalonia 11.3.x lets unobserved task exceptions reach the
            // dispatcher and kill the process; route them to the logger
            // instead so background D-Bus failures don't take the GUI down.
            TaskScheduler.UnobservedTaskException += static (sender, args) =>
            {
                Console.Error.WriteLine($"[unobserved-task] {args.Exception}");
                args.SetObserved();
            };

            var services = new ServiceCollection();
            services.AddLogging(builder =>
            {
                builder.SetMinimumLevel(LogLevel.Information);
                if (JournaldLoggingExtensions.IsJournaldDetected())
                {
                    // systemd / journald style for autostart + Flathub launches
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
            services.AddSingleton<IAutoStartManager, PortalAutostartManager>();
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
            services.AddSingleton<MainWindowViewModel>();
            services.AddSingleton<ShellViewModel>();
            var provider = services.BuildServiceProvider();
            Services = provider;

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
                Avalonia.Threading.Dispatcher.UIThread.Post(() => desktop.Shutdown(0));
                return;
            }

            // The Avalonia MainWindow expects MainWindowViewModel as its
            // DataContext (mirrors the WPF head); the LocalizationProxy is
            // resolved here purely for its side-effect of subscribing to
            // LocalizationService.LanguageChanged so the {StaticResource Loc}
            // bindings refresh when the language switches.
            _ = provider.GetRequiredService<LocalizationProxy>();
            var viewModel = provider.GetRequiredService<MainWindowViewModel>();
            viewModel.ProductVersionText =
                $"v{typeof(App).Assembly.GetName().Version?.ToString(3) ?? "0.0.0"}";
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
            _trayHost.QuitRequested += (_, _) => desktop.Shutdown(0);
            _trayHost.TrayUnavailable += (_, _) => Avalonia.Threading.Dispatcher.UIThread.Post(() =>
            {
                viewModel.TrayStatusMessage = ImmichFolderWatch.App.Shared.Resources.Strings.Tray_Unavailable;
                // If we started hidden (autostart) but the tray fails,
                // surface the GUI so the user can see the app is alive
                // — otherwise it'd be running invisibly with no entry
                // point until they relaunched the .desktop file.
                if (startHidden && _mainWindow is { IsVisible: false })
                {
                    _mainWindow.Show();
                    _mainWindow.Activate();
                }
            });
            _ = _trayHost.StartAsync(this);

            // ClassicDesktopStyleApplicationLifetime.Start() auto-Show()s
            // whatever is assigned to MainWindow once we return from
            // OnFrameworkInitializationCompleted. To honour --background
            // we simply leave it unassigned: ShutdownMode.OnExplicitShutdown
            // keeps the dispatcher loop alive, and the tray-click /
            // second-instance-handoff callbacks above will Show() the
            // window when the user actually wants it.
            if (!startHidden)
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
            desktop.Exit += async (_, _) =>
            {
                _trayHost?.Dispose();
                if (provider is IAsyncDisposable asyncDisposable)
                {
                    await asyncDisposable.DisposeAsync();
                }
                else if (provider is IDisposable disposable)
                {
                    disposable.Dispose();
                }
            };
        }

        base.OnFrameworkInitializationCompleted();
    }
}
