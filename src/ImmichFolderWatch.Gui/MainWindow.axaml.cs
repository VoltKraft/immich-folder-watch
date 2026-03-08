using System.ComponentModel;
using System.Diagnostics;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Threading;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Gui.Models;
using ImmichFolderWatch.Gui.Services;
using ImmichFolderWatch.Gui.ViewModels;

namespace ImmichFolderWatch.Gui;

public sealed partial class MainWindow : Window
{
    private readonly AdminCliClient _adminCliClient;
    private readonly ConfigVerificationRunner _verificationRunner;
    private readonly AppConfigLoader _configLoader;
    private readonly DispatcherTimer _statusRefreshTimer;
    private bool _isStatusRefreshInProgress;

    public MainWindow()
    {
        InitializeComponent();

        _adminCliClient = new AdminCliClient(InstallationPaths.GetAdminExecutablePath(AppContext.BaseDirectory));
        _verificationRunner = new ConfigVerificationRunner();
        _configLoader = new AppConfigLoader();
        _statusRefreshTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(10),
        };
        _statusRefreshTimer.Tick += StatusRefreshTimer_Tick;

        ViewModel = new MainWindowViewModel();
        DataContext = ViewModel;
        Closed += MainWindow_Closed;
    }

    private MainWindowViewModel ViewModel { get; }

    protected override async void OnOpened(EventArgs e)
    {
        base.OnOpened(e);
        await LoadAsync();
        _statusRefreshTimer.Start();
    }

    private async Task LoadAsync()
    {
        var statusResponse = await RefreshStatusAsync(updateOperationMessageOnFailure: true);
        LoadConfigFromDisk(statusResponse?.Status?.ConfigPath ?? InstallationPaths.GetConfigPath(AppContext.BaseDirectory));
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
            ViewModel.OperationMessage = $"The existing config could not be loaded. Defaults were opened instead: {ex.Message}";
        }
    }

    private static AppConfig CreateDefaultConfig()
    {
        return new AppConfig
        {
            Logging = new LoggingSettings
            {
                Level = "Information",
                LogDirectory = Path.GetFullPath(InstallationPaths.GetLogDirectory(AppContext.BaseDirectory)),
            },
        };
    }

    private static void NormalizeLogDirectoryForEditing(AppConfig config, string configPath)
    {
        config.Logging ??= new LoggingSettings();

        if (string.IsNullOrWhiteSpace(config.Logging.LogDirectory))
        {
            config.Logging.LogDirectory = Path.GetFullPath(InstallationPaths.GetLogDirectory(AppContext.BaseDirectory));
            return;
        }

        if (Path.IsPathFullyQualified(config.Logging.LogDirectory))
        {
            config.Logging.LogDirectory = Path.GetFullPath(config.Logging.LogDirectory);
            return;
        }

        var configDirectory = Path.GetDirectoryName(Path.GetFullPath(configPath)) ?? AppContext.BaseDirectory;
        config.Logging.LogDirectory = Path.GetFullPath(Path.Combine(configDirectory, config.Logging.LogDirectory));
    }

    private void ApplyStatus(ServiceStatusSnapshot? status)
    {
        if (status is null)
        {
            ViewModel.StatusHeadline = "Service status unavailable";
            ViewModel.StatusDetails = "The admin helper did not return any status information.";
            return;
        }

        var startupType = status.StartupType == ServiceStartupType.Automatic && status.DelayedAutoStart
            ? "Automatic (Delayed Start)"
            : status.StartupType.ToString();

        ViewModel.StatusHeadline = status.Exists
            ? $"Service: {status.State}"
            : "Service is not installed";

        ViewModel.StatusDetails =
            $"Startup: {startupType}{Environment.NewLine}" +
            $"Verified: {(status.IsInitialVerificationCompleted ? "Yes" : "No")}{Environment.NewLine}" +
            $"Config: {status.ConfigPath}{Environment.NewLine}" +
            $"Logs: {status.LogDirectory}";
    }

    private async Task<AdminCommandResponse?> RefreshStatusAsync(bool updateOperationMessageOnFailure, string? successMessage = null)
    {
        if (_isStatusRefreshInProgress)
        {
            return null;
        }

        _isStatusRefreshInProgress = true;

        try
        {
            var statusResponse = await _adminCliClient.GetStatusAsync(CancellationToken.None);
            ApplyStatus(statusResponse.Status);

            if (!string.IsNullOrWhiteSpace(successMessage))
            {
                ViewModel.OperationMessage = successMessage;
            }

            return statusResponse;
        }
        catch (Exception ex)
        {
            ApplyStatus(null);
            if (updateOperationMessageOnFailure)
            {
                ViewModel.OperationMessage = $"Failed to load current status: {ex.Message}";
            }

            return null;
        }
        finally
        {
            _isStatusRefreshInProgress = false;
        }
    }

    private async void RefreshStatusButton_Click(object? sender, RoutedEventArgs e)
    {
        await RefreshStatusAsync(updateOperationMessageOnFailure: true, successMessage: "Service status refreshed.");
    }

    private void AddSourceButton_Click(object? sender, RoutedEventArgs e)
    {
        ViewModel.Sources.Add(new WatchSourceItem());
    }

    private void RemoveSourceButton_Click(object? sender, RoutedEventArgs e)
    {
        if (sender is Button { DataContext: WatchSourceItem source })
        {
            ViewModel.Sources.Remove(source);
        }
    }

    private void OpenLogsButton_Click(object? sender, RoutedEventArgs e)
    {
        var logDirectory = ViewModel.GetEffectiveLogDirectory();
        if (string.IsNullOrWhiteSpace(logDirectory))
        {
            ViewModel.OperationMessage = "No log directory is configured.";
            return;
        }

        var fullPath = Path.IsPathFullyQualified(logDirectory)
            ? Path.GetFullPath(logDirectory)
            : Path.GetFullPath(Path.Combine(Path.GetDirectoryName(InstallationPaths.GetConfigPath(AppContext.BaseDirectory)) ?? AppContext.BaseDirectory, logDirectory));

        if (!Directory.Exists(fullPath))
        {
            ViewModel.OperationMessage = $"The log directory does not exist: {fullPath}";
            return;
        }

        Process.Start(new ProcessStartInfo
        {
            FileName = fullPath,
            UseShellExecute = true,
        });
    }

    private void UseDefaultLogDirectoryButton_Click(object? sender, RoutedEventArgs e)
    {
        ViewModel.LogDirectory = Path.GetFullPath(InstallationPaths.GetLogDirectory(AppContext.BaseDirectory));
        ViewModel.OperationMessage = "Log directory reset to the default install path.";
    }

    private async void SaveAndVerifyButton_Click(object? sender, RoutedEventArgs e)
    {
        if (!ViewModel.TryCreateConfig(out var draftConfig, out var inputErrors))
        {
            ViewModel.OperationMessage = string.Join(Environment.NewLine, inputErrors);
            return;
        }

        var tempConfigPath = Path.Combine(Path.GetTempPath(), $"ifw-config-{Guid.NewGuid():N}.yaml");
        try
        {
            _statusRefreshTimer.Stop();

            var writer = new AppConfigWriter();
            File.WriteAllText(tempConfigPath, writer.Serialize(draftConfig));

            ViewModel.OperationMessage = "Verifying configuration against Immich...";
            var verificationResult = await _verificationRunner.VerifyAsync(
                draftConfig,
                InstallationPaths.GetConfigPath(AppContext.BaseDirectory),
                CancellationToken.None);
            if (!verificationResult.Success)
            {
                ViewModel.OperationMessage = string.Join(Environment.NewLine, verificationResult.Errors);
                return;
            }

            ViewModel.OperationMessage = "Applying configuration with elevated permissions...";
            var response = await _adminCliClient.ApplyVerifiedConfigAsync(tempConfigPath, CancellationToken.None);
            ApplyStatus(response.Status);
            if (response.Success)
            {
                LoadConfigFromDisk(response.Status?.ConfigPath ?? InstallationPaths.GetConfigPath(AppContext.BaseDirectory));
            }
            ViewModel.OperationMessage = response.Message;
        }
        catch (OperationCanceledException)
        {
            ViewModel.OperationMessage = "The elevation prompt was canceled.";
        }
        catch (Win32Exception ex) when (ex.NativeErrorCode == 1223)
        {
            ViewModel.OperationMessage = "The elevation prompt was canceled.";
        }
        catch (Exception ex)
        {
            ViewModel.OperationMessage = $"Saving the config failed: {ex.Message}";
        }
        finally
        {
            _statusRefreshTimer.Start();

            if (File.Exists(tempConfigPath))
            {
                File.Delete(tempConfigPath);
            }
        }
    }

    private async void StatusRefreshTimer_Tick(object? sender, EventArgs e)
    {
        await RefreshStatusAsync(updateOperationMessageOnFailure: false);
    }

    private void MainWindow_Closed(object? sender, EventArgs e)
    {
        _statusRefreshTimer.Stop();
    }
}
