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
            services.AddSingleton<AvaloniaTrayHost>();
            services.AddSingleton<PortalFolderPicker>(sp =>
                new PortalFolderPicker(
                    () => _mainWindow,
                    sp.GetRequiredService<ILogger<PortalFolderPicker>>()));
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
            _ = _trayHost.StartAsync(this);

            desktop.MainWindow = _mainWindow;
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
