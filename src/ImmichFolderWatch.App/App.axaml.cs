using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Avalonia.Platform;
using Avalonia.Threading;
using ImmichFolderWatch.App.Hosting;
using ImmichFolderWatch.App.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.App;

public sealed partial class App : Application
{
    private readonly SyncStatusProvider _syncStatusProvider = new();
    private readonly AutostartManager _autostartManager = new();
    private readonly AppConfigLoader _configLoader = new();
    private readonly AppHost _appHost;

    private TrayIcon? _trayIcon;
    private NativeMenuItem? _openGuiMenuItem;
    private NativeMenuItem? _restartSyncMenuItem;
    private NativeMenuItem? _quitMenuItem;
    private MainWindow? _mainWindow;
    private bool _explicitQuitRequested;

    public App()
    {
        _appHost = new AppHost(_syncStatusProvider);
        _syncStatusProvider.PropertyChanged += SyncStatusProvider_PropertyChanged;
    }

    public SyncStatusProvider SyncStatusProvider => _syncStatusProvider;

    public AutostartManager AutostartManager => _autostartManager;

    public AppHost AppHost => _appHost;

    public AppConfigLoader ConfigLoader => _configLoader;

    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.ShutdownMode = ShutdownMode.OnExplicitShutdown;
            desktop.Exit += OnDesktopExit;

            _mainWindow = new MainWindow(_appHost, _syncStatusProvider, _autostartManager, _configLoader);
            _mainWindow.Closing += MainWindow_Closing;
            desktop.MainWindow = _mainWindow;

            InitializeTrayIcon();

            if (!Program.StartHiddenForAutostart)
            {
                _mainWindow.Show();
            }

            Program.SingleInstance?.StartListening(ShowMainWindow);

            _ = StartAppHostAsync();

            if (!_autostartManager.IsEnabled() && IsFirstRun())
            {
                try
                {
                    _autostartManager.Enable();
                }
                catch (Exception)
                {
                }
            }
        }

        base.OnFrameworkInitializationCompleted();
    }

    private async Task StartAppHostAsync()
    {
        try
        {
            var configPath = InstallationPaths.GetConfigPath();
            if (!File.Exists(configPath))
            {
                return;
            }

            var config = _configLoader.Load(configPath);
            var validationErrors = AppConfigValidator.Validate(config);
            if (validationErrors.Count > 0)
            {
                return;
            }

            await _appHost.StartAsync(config);
        }
        catch (Exception)
        {
        }
    }

    private void InitializeTrayIcon()
    {
        var icon = LoadTrayIcon();
        var menu = new NativeMenu();

        _openGuiMenuItem = new NativeMenuItem("GUI öffnen");
        _openGuiMenuItem.Click += (_, _) => ShowMainWindow();

        _restartSyncMenuItem = new NativeMenuItem("Neustart");
        _restartSyncMenuItem.Click += (_, _) => _ = RestartSyncAsync();

        _quitMenuItem = new NativeMenuItem("Beenden");
        _quitMenuItem.Click += (_, _) => _ = QuitAsync();

        menu.Add(_openGuiMenuItem);
        menu.Add(new NativeMenuItemSeparator());
        menu.Add(_restartSyncMenuItem);
        menu.Add(new NativeMenuItemSeparator());
        menu.Add(_quitMenuItem);

        _trayIcon = new TrayIcon
        {
            Icon = icon,
            ToolTipText = _syncStatusProvider.TooltipText,
            Menu = menu,
            IsVisible = true,
        };
        _trayIcon.Clicked += (_, _) => ShowMainWindow();

        TrayIcon.SetIcons(this, new TrayIcons { _trayIcon });
    }

    private static WindowIcon? LoadTrayIcon()
    {
        try
        {
            using var stream = AssetLoader.Open(new Uri("avares://ImmichFolderWatch.App/Assets/app-icon.ico"));
            return new WindowIcon(stream);
        }
        catch (Exception)
        {
            return null;
        }
    }

    private void SyncStatusProvider_PropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (!string.Equals(e.PropertyName, nameof(SyncStatusProvider.TooltipText), StringComparison.Ordinal))
        {
            return;
        }

        if (_trayIcon is null)
        {
            return;
        }

        Dispatcher.UIThread.Post(() =>
        {
            if (_trayIcon is not null)
            {
                _trayIcon.ToolTipText = _syncStatusProvider.TooltipText;
            }
        });
    }

    private void ShowMainWindow()
    {
        Dispatcher.UIThread.Post(() =>
        {
            if (_mainWindow is null)
            {
                return;
            }

            if (!_mainWindow.IsVisible)
            {
                _mainWindow.Show();
            }

            if (_mainWindow.WindowState == WindowState.Minimized)
            {
                _mainWindow.WindowState = WindowState.Normal;
            }

            _mainWindow.Activate();
        });
    }

    private async Task RestartSyncAsync()
    {
        var config = _appHost.CurrentConfig;
        if (config is null)
        {
            return;
        }

        try
        {
            await _appHost.RestartAsync(config);
        }
        catch (Exception)
        {
        }
    }

    private async Task QuitAsync()
    {
        _explicitQuitRequested = true;

        try
        {
            await _appHost.StopAsync();
        }
        catch (Exception)
        {
        }

        Dispatcher.UIThread.Post(() =>
        {
            if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
            {
                desktop.Shutdown(0);
            }
        });
    }

    private void MainWindow_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        if (_explicitQuitRequested)
        {
            return;
        }

        e.Cancel = true;
        _mainWindow?.Hide();
    }

    private void OnDesktopExit(object? sender, ControlledApplicationLifetimeExitEventArgs e)
    {
        if (_trayIcon is not null)
        {
            _trayIcon.IsVisible = false;
            _trayIcon.Dispose();
            _trayIcon = null;
        }

        try
        {
            _appHost.DisposeAsync().AsTask().GetAwaiter().GetResult();
        }
        catch (Exception)
        {
        }
    }

    private static bool IsFirstRun()
    {
        return !File.Exists(InstallationPaths.GetConfigPath());
    }
}
