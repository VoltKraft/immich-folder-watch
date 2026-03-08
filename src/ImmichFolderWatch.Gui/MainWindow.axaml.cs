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
    private bool _isImmichCheckInProgress;

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
        ViewModel.ProductVersionText = $"Version {ProductVersionProvider.GetProductVersion()}";
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
            ViewModel.ServiceBadgeText = "Unavailable";
            ViewModel.ServiceBadgeBackground = "#E0E3E8";
            ViewModel.ApplyServiceActionVisibility(null);
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
            $"Config: {status.ConfigPath}{Environment.NewLine}" +
            $"Logs: {status.LogDirectory}";

        ApplyServiceBadge(status);
        ViewModel.ApplyServiceActionVisibility(status);
    }

    private void ApplyServiceBadge(ServiceStatusSnapshot status)
    {
        if (!status.Exists)
        {
            ViewModel.ServiceBadgeText = "Not installed";
            ViewModel.ServiceBadgeBackground = "#E0E3E8";
            return;
        }

        switch (status.State)
        {
            case ServiceRunState.Running:
                ViewModel.ServiceBadgeText = "Running";
                ViewModel.ServiceBadgeBackground = "#D8F0D9";
                break;
            case ServiceRunState.Stopped:
                ViewModel.ServiceBadgeText = "Stopped";
                ViewModel.ServiceBadgeBackground = "#F9E3B4";
                break;
            case ServiceRunState.StartPending:
                ViewModel.ServiceBadgeText = "Starting";
                ViewModel.ServiceBadgeBackground = "#D7E8FF";
                break;
            case ServiceRunState.StopPending:
                ViewModel.ServiceBadgeText = "Stopping";
                ViewModel.ServiceBadgeBackground = "#D7E8FF";
                break;
            default:
                ViewModel.ServiceBadgeText = "Unknown";
                ViewModel.ServiceBadgeBackground = "#E0E3E8";
                break;
        }
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
                ViewModel.OperationMessage = "Checking Immich URL, API key, and permissions...";
            }

            var accessResult = await _verificationRunner.CheckImmichAccessAsync(
                ViewModel.CreateImmichCheckConfig(),
                InstallationPaths.GetConfigPath(AppContext.BaseDirectory),
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
            ViewModel.OperationMessage = $"Immich access check failed: {ex.Message}";
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
            CheckState.Passed => "Immich access check completed successfully.",
            CheckState.Warning => accessResult.PermissionsMessage,
            CheckState.Failed => accessResult.PermissionsMessage,
            _ => "Immich access check completed.",
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

    private async Task ExecuteServiceActionAsync(
        Func<CancellationToken, Task<AdminCommandResponse>> action,
        string pendingMessage)
    {
        try
        {
            _statusRefreshTimer.Stop();
            ViewModel.OperationMessage = pendingMessage;

            var response = await action(CancellationToken.None);
            ApplyStatus(response.Status);
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
            ViewModel.OperationMessage = $"Service action failed: {ex.Message}";
        }
        finally
        {
            _statusRefreshTimer.Start();
        }
    }

    private async void VerifyImmichButton_Click(object? sender, RoutedEventArgs e)
    {
        await RunImmichAccessCheckAsync(updateOperationMessage: true);
    }

    private async void StartServiceButton_Click(object? sender, RoutedEventArgs e)
    {
        await ExecuteServiceActionAsync(_adminCliClient.StartServiceAsync, "Starting service...");
    }

    private async void StopServiceButton_Click(object? sender, RoutedEventArgs e)
    {
        await ExecuteServiceActionAsync(_adminCliClient.StopServiceAsync, "Stopping service...");
    }

    private async void RestartServiceButton_Click(object? sender, RoutedEventArgs e)
    {
        await ExecuteServiceActionAsync(_adminCliClient.RestartServiceAsync, "Restarting service...");
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

    private async void SaveActionButton_Click(object? sender, RoutedEventArgs e)
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

            ViewModel.SetImmichCheckInProgress();
            ViewModel.OperationMessage = "Verifying configuration against Immich...";

            var accessResult = await _verificationRunner.CheckImmichAccessAsync(
                draftConfig,
                InstallationPaths.GetConfigPath(AppContext.BaseDirectory),
                CancellationToken.None);
            ViewModel.ApplyImmichCheckResult(accessResult);

            var verificationResult = _verificationRunner.BuildVerificationResult(
                draftConfig,
                InstallationPaths.GetConfigPath(AppContext.BaseDirectory),
                accessResult);

            if (!verificationResult.Success)
            {
                ViewModel.OperationMessage = string.Join(Environment.NewLine, verificationResult.Errors);
                return;
            }

            ViewModel.OperationMessage = BuildSaveActionPendingMessage();
            var response = await _adminCliClient.ApplyVerifiedConfigAsync(tempConfigPath, CancellationToken.None);
            ApplyStatus(response.Status);
            if (response.Success)
            {
                LoadConfigFromDisk(response.Status?.ConfigPath ?? InstallationPaths.GetConfigPath(AppContext.BaseDirectory));
                await RunImmichAccessCheckAsync(updateOperationMessage: false);
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

    private string BuildSaveActionPendingMessage()
    {
        return ViewModel.SaveActionButtonText == "Save and Restart"
            ? "Applying configuration with elevated permissions and restarting the service..."
            : "Applying configuration with elevated permissions and starting the service...";
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
