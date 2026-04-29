using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using ImmichFolderWatch.App.Linux.Platform;
using ImmichFolderWatch.App.Linux.ViewModels;
using ImmichFolderWatch.App.Linux.Views;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.App.Linux;

public sealed partial class App : Application
{
    private MainWindow? _mainWindow;
    private AvaloniaTrayHost? _trayHost;

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
            services.AddSingleton<AvaloniaTrayHost>();
            services.AddSingleton<PortalFolderPicker>(sp =>
                new PortalFolderPicker(
                    () => _mainWindow,
                    sp.GetRequiredService<ILogger<PortalFolderPicker>>()));
            services.AddSingleton<ShellViewModel>();
            var provider = services.BuildServiceProvider();

            var single = provider.GetRequiredService<ISingleInstanceCoordinator>();
            if (!single.IsPrimaryInstance)
            {
                single.TrySignalShowGui(TimeSpan.FromSeconds(2));
                desktop.Shutdown(0);
                return;
            }

            _mainWindow = new MainWindow
            {
                DataContext = provider.GetRequiredService<ShellViewModel>(),
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
