using System.ComponentModel;
using System.Windows;
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
    private readonly LocalizationService _localizationService = LocalizationService.Instance;
    private readonly AppHost _appHost;
    private readonly ThemeWatcher _themeWatcher;

    private TrayIconHost? _trayIconHost;
    private MainWindow? _mainWindow;
    private bool _explicitQuitRequested;

    public App()
    {
        _appHost = new AppHost(_syncStatusProvider);
        _themeWatcher = new ThemeWatcher(this);
    }

    public SyncStatusProvider SyncStatusProvider => _syncStatusProvider;

    public AutostartManager AutostartManager => _autostartManager;

    public AppHost AppHost => _appHost;

    public AppConfigLoader ConfigLoader => _configLoader;

    public ThemeWatcher ThemeWatcher => _themeWatcher;

    public LocalizationService LocalizationService => _localizationService;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        ApplyStartupLanguage();

        _themeWatcher.Initialize();

        _mainWindow = new MainWindow(_appHost, _syncStatusProvider, _autostartManager, _configLoader, _themeWatcher, _localizationService);
        _mainWindow.Closing += MainWindow_Closing;
        MainWindow = _mainWindow;

        SessionEnding += OnSessionEnding;

        _trayIconHost = new TrayIconHost(_syncStatusProvider, _themeWatcher, _localizationService);
        _trayIconHost.OpenGuiRequested += ShowMainWindow;
        _trayIconHost.RestartRequested += () => _ = RestartSyncAsync();
        _trayIconHost.QuitRequested += () => _ = QuitAsync();

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

    protected override void OnExit(ExitEventArgs e)
    {
        if (_trayIconHost is not null)
        {
            _trayIconHost.Dispose();
            _trayIconHost = null;
        }

        try
        {
            _appHost.DisposeAsync().AsTask().GetAwaiter().GetResult();
        }
        catch (Exception)
        {
        }

        base.OnExit(e);
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

    private void ShowMainWindow()
    {
        Dispatcher.BeginInvoke(new Action(() =>
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
            _mainWindow.Topmost = true;
            _mainWindow.Topmost = false;
            _mainWindow.Focus();
        }));
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

        _ = Dispatcher.BeginInvoke(new Action(() => Shutdown(0)));
    }

    private void MainWindow_Closing(object? sender, CancelEventArgs e)
    {
        if (_explicitQuitRequested)
        {
            return;
        }

        e.Cancel = true;
        _mainWindow?.Hide();
    }

    private void OnSessionEnding(object? sender, SessionEndingCancelEventArgs e)
    {
        _ = QuitAsync();
    }

    private static bool IsFirstRun()
    {
        return !File.Exists(InstallationPaths.GetConfigPath());
    }

    private void ApplyStartupLanguage()
    {
        var language = LocalizationService.LanguageAuto;
        try
        {
            var configPath = InstallationPaths.GetConfigPath();
            if (File.Exists(configPath))
            {
                var config = _configLoader.LoadForEditing(configPath);
                language = config.Localization?.Language ?? LocalizationService.LanguageAuto;
            }
        }
        catch (Exception)
        {
        }

        _localizationService.SetLanguage(language);
    }
}
