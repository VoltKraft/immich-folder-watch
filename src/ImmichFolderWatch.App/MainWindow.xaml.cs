using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using Button = System.Windows.Controls.Button;
using ImmichFolderWatch.App.Hosting;
using ImmichFolderWatch.App.Models;
using ImmichFolderWatch.App.Services;
using ImmichFolderWatch.App.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.App;

public sealed partial class MainWindow : Window
{
    private const int WM_SETTINGCHANGE = 0x001A;
    private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);

    private readonly AppHost _appHost;
    private readonly SyncStatusProvider _syncStatusProvider;
    private readonly AutostartManager _autostartManager;
    private readonly AppConfigLoader _configLoader;
    private readonly ThemeWatcher _themeWatcher;
    private readonly ConfigVerificationRunner _verificationRunner;
    private bool _isImmichCheckInProgress;
    private bool _isSaveInProgress;
    private bool _hasRunInitialLoad;

    public MainWindow(
        AppHost appHost,
        SyncStatusProvider syncStatusProvider,
        AutostartManager autostartManager,
        AppConfigLoader configLoader,
        ThemeWatcher themeWatcher)
    {
        _appHost = appHost ?? throw new ArgumentNullException(nameof(appHost));
        _syncStatusProvider = syncStatusProvider ?? throw new ArgumentNullException(nameof(syncStatusProvider));
        _autostartManager = autostartManager ?? throw new ArgumentNullException(nameof(autostartManager));
        _configLoader = configLoader ?? throw new ArgumentNullException(nameof(configLoader));
        _themeWatcher = themeWatcher ?? throw new ArgumentNullException(nameof(themeWatcher));
        _verificationRunner = new ConfigVerificationRunner();

        InitializeComponent();

        ViewModel = new MainWindowViewModel(_syncStatusProvider, _autostartManager)
        {
            ProductVersionText = $"Version {ProductVersionProvider.GetProductVersion()}",
        };
        DataContext = ViewModel;

        Loaded += OnLoaded;
        SourceInitialized += OnSourceInitialized;
        _themeWatcher.ThemeChanged += OnThemeChanged;
        Closed += OnClosed;
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        var source = PresentationSource.FromVisual(this) as HwndSource;
        source?.AddHook(WndProc);
        ApplyDarkTitleBar();
    }

    private void OnClosed(object? sender, EventArgs e)
    {
        _themeWatcher.ThemeChanged -= OnThemeChanged;
    }

    private void OnThemeChanged(object? sender, EventArgs e)
    {
        ApplyDarkTitleBar();
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == WM_SETTINGCHANGE)
        {
            _themeWatcher.Refresh();
        }

        return IntPtr.Zero;
    }

    private void ApplyDarkTitleBar()
    {
        var helper = new WindowInteropHelper(this);
        var hwnd = helper.Handle;
        if (hwnd == IntPtr.Zero)
        {
            return;
        }

        int useDark = _themeWatcher.IsDark ? 1 : 0;
        DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ref useDark, sizeof(int));
    }

    private MainWindowViewModel ViewModel { get; }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (_hasRunInitialLoad)
        {
            return;
        }

        _hasRunInitialLoad = true;

        ViewModel.RefreshAutostartFromDisk();
        LoadConfigFromDisk(InstallationPaths.GetConfigPath());
        await RunImmichAccessCheckAsync(updateOperationMessage: false);
    }

    private void LoadConfigFromDisk(string configPath)
    {
        if (!File.Exists(configPath))
        {
            ViewModel.Load(CreateDefaultConfig());
            return;
        }

        try
        {
            var config = _configLoader.LoadForEditing(configPath);
            NormalizeLogDirectoryForEditing(config, configPath);
            ViewModel.Load(config);
        }
        catch (Exception ex)
        {
            ViewModel.Load(CreateDefaultConfig());
            ViewModel.OperationMessage = $"Die bestehende Konfiguration konnte nicht geladen werden. Standardwerte wurden geöffnet: {ex.Message}";
        }
    }

    private static AppConfig CreateDefaultConfig()
    {
        return new AppConfig
        {
            Logging = new LoggingSettings
            {
                Level = "Information",
                LogDirectory = Path.GetFullPath(InstallationPaths.GetLogDirectory()),
            },
        };
    }

    private static void NormalizeLogDirectoryForEditing(AppConfig config, string configPath)
    {
        config.Logging ??= new LoggingSettings();

        if (string.IsNullOrWhiteSpace(config.Logging.LogDirectory))
        {
            config.Logging.LogDirectory = Path.GetFullPath(InstallationPaths.GetLogDirectory());
            return;
        }

        if (Path.IsPathFullyQualified(config.Logging.LogDirectory))
        {
            config.Logging.LogDirectory = Path.GetFullPath(config.Logging.LogDirectory);
            return;
        }

        var configDirectory = Path.GetDirectoryName(Path.GetFullPath(configPath))
            ?? Path.GetDirectoryName(InstallationPaths.GetConfigPath())
            ?? AppContext.BaseDirectory;
        config.Logging.LogDirectory = Path.GetFullPath(Path.Combine(configDirectory, config.Logging.LogDirectory));
    }

    private async Task RunImmichAccessCheckAsync(bool updateOperationMessage)
    {
        if (_isImmichCheckInProgress)
        {
            return;
        }

        _isImmichCheckInProgress = true;

        try
        {
            ViewModel.SetImmichCheckInProgress();

            if (updateOperationMessage)
            {
                ViewModel.OperationMessage = "Prüfe Immich-URL, API-Key und Berechtigungen...";
            }

            var accessResult = await _verificationRunner.CheckImmichAccessAsync(
                ViewModel.CreateImmichCheckConfig(),
                InstallationPaths.GetConfigPath(),
                CancellationToken.None);

            ViewModel.ApplyImmichCheckResult(accessResult);

            if (updateOperationMessage)
            {
                ViewModel.OperationMessage = BuildImmichCheckSummary(accessResult);
            }
        }
        catch (Exception ex)
        {
            ViewModel.ApplyImmichCheckResult(CreateUnexpectedImmichCheckFailureResult(ex.Message));
            ViewModel.OperationMessage = $"Immich-Prüfung ist fehlgeschlagen: {ex.Message}";
        }
        finally
        {
            _isImmichCheckInProgress = false;
        }
    }

    private static string BuildImmichCheckSummary(ImmichAccessCheckResult accessResult)
    {
        if (accessResult.UrlState == CheckState.Failed)
        {
            return accessResult.UrlMessage;
        }

        if (accessResult.ApiKeyState == CheckState.Failed)
        {
            return accessResult.ApiKeyMessage;
        }

        return accessResult.PermissionsState switch
        {
            CheckState.Passed => "Immich-Zugangsprüfung erfolgreich abgeschlossen.",
            CheckState.Warning => accessResult.PermissionsMessage,
            CheckState.Failed => accessResult.PermissionsMessage,
            _ => "Immich-Zugangsprüfung abgeschlossen.",
        };
    }

    private static ImmichAccessCheckResult CreateUnexpectedImmichCheckFailureResult(string message)
    {
        const string notCheckedMessage = "Not checked because the Immich access check failed unexpectedly.";

        return new ImmichAccessCheckResult
        {
            UrlState = CheckState.Failed,
            UrlMessage = $"Immich access check failed unexpectedly: {message}",
            ApiKeyState = CheckState.NotChecked,
            ApiKeyMessage = notCheckedMessage,
            PermissionsState = CheckState.NotChecked,
            PermissionsMessage = notCheckedMessage,
            PermissionResults =
            [
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Asset Upload",
                    PermissionName = "asset.upload",
                    State = CheckState.NotChecked,
                    Message = notCheckedMessage,
                    BlocksConfigVerification = true,
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Album Read",
                    PermissionName = "album.read",
                    State = CheckState.NotChecked,
                    Message = notCheckedMessage,
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Album Create",
                    PermissionName = "album.create",
                    State = CheckState.NotChecked,
                    Message = notCheckedMessage,
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Add Asset To Album",
                    PermissionName = "albumAsset.create",
                    State = CheckState.NotChecked,
                    Message = notCheckedMessage,
                },
            ],
        };
    }

    private async void VerifyImmichButton_Click(object sender, RoutedEventArgs e)
    {
        await RunImmichAccessCheckAsync(updateOperationMessage: true);
    }

    private void ToggleApiKeyVisibilityButton_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.ToggleImmichApiKeyVisibility();
    }

    private void AddSourceButton_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.AddSource();
    }

    private void RemoveSourceButton_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button { DataContext: WatchSourceItem source })
        {
            ViewModel.Sources.Remove(source);
        }
    }

    private void OpenLogsButton_Click(object sender, RoutedEventArgs e)
    {
        var logDirectory = ViewModel.GetEffectiveLogDirectory();
        if (string.IsNullOrWhiteSpace(logDirectory))
        {
            ViewModel.OperationMessage = "Kein Log-Verzeichnis konfiguriert.";
            return;
        }

        var fullPath = Path.IsPathFullyQualified(logDirectory)
            ? Path.GetFullPath(logDirectory)
            : Path.GetFullPath(Path.Combine(
                Path.GetDirectoryName(InstallationPaths.GetConfigPath()) ?? AppContext.BaseDirectory,
                logDirectory));

        if (!Directory.Exists(fullPath))
        {
            ViewModel.OperationMessage = $"Das Log-Verzeichnis existiert nicht: {fullPath}";
            return;
        }

        Process.Start(new ProcessStartInfo
        {
            FileName = fullPath,
            UseShellExecute = true,
        });
    }

    private void UseDefaultLogDirectoryButton_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.LogDirectory = Path.GetFullPath(InstallationPaths.GetLogDirectory());
        ViewModel.OperationMessage = "Log-Verzeichnis auf den Standardpfad zurückgesetzt.";
    }

    private async void SaveActionButton_Click(object sender, RoutedEventArgs e)
    {
        if (_isSaveInProgress)
        {
            return;
        }

        if (!ViewModel.TryCreateConfig(out var draftConfig, out var inputErrors))
        {
            ViewModel.OperationMessage = string.Join(Environment.NewLine, inputErrors);
            return;
        }

        _isSaveInProgress = true;
        try
        {
            var configPath = InstallationPaths.GetConfigPath();

            ViewModel.SetImmichCheckInProgress();
            ViewModel.OperationMessage = "Prüfe Konfiguration gegen Immich...";

            var accessResult = await _verificationRunner.CheckImmichAccessAsync(
                draftConfig,
                configPath,
                CancellationToken.None);
            ViewModel.ApplyImmichCheckResult(accessResult);

            var verificationResult = _verificationRunner.BuildVerificationResult(
                draftConfig,
                configPath,
                accessResult);

            if (!verificationResult.Success)
            {
                ViewModel.OperationMessage = string.Join(Environment.NewLine, verificationResult.Errors);
                return;
            }

            ViewModel.OperationMessage = "Speichere Konfiguration und starte Sync neu...";

            var configDirectory = Path.GetDirectoryName(configPath);
            if (!string.IsNullOrWhiteSpace(configDirectory))
            {
                Directory.CreateDirectory(configDirectory);
            }

            var yaml = new AppConfigWriter().Serialize(draftConfig);
            await File.WriteAllTextAsync(configPath, yaml);

            await _appHost.RestartAsync(draftConfig);

            LoadConfigFromDisk(configPath);
            ViewModel.OperationMessage = "Konfiguration gespeichert und angewendet.";
        }
        catch (Exception ex)
        {
            ViewModel.OperationMessage = $"Speichern fehlgeschlagen: {ex.Message}";
        }
        finally
        {
            _isSaveInProgress = false;
        }
    }
}
