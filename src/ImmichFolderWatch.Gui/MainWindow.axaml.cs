using System.ComponentModel;
using System.Diagnostics;
using Avalonia.Controls;
using Avalonia.Interactivity;
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

    public MainWindow()
    {
        InitializeComponent();

        _adminCliClient = new AdminCliClient(InstallationPaths.GetAdminExecutablePath(AppContext.BaseDirectory));
        _verificationRunner = new ConfigVerificationRunner();
        _configLoader = new AppConfigLoader();

        ViewModel = new MainWindowViewModel();
        DataContext = ViewModel;
    }

    private MainWindowViewModel ViewModel { get; }

    protected override async void OnOpened(EventArgs e)
    {
        base.OnOpened(e);
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        try
        {
            var statusResponse = await _adminCliClient.GetStatusAsync(CancellationToken.None);
            ApplyStatus(statusResponse.Status);
            LoadConfigFromDisk(statusResponse.Status?.ConfigPath ?? InstallationPaths.GetConfigPath(AppContext.BaseDirectory));
            ViewModel.OperationMessage = statusResponse.Message;
        }
        catch (Exception ex)
        {
            ApplyStatus(null);
            LoadConfigFromDisk(InstallationPaths.GetConfigPath(AppContext.BaseDirectory));
            ViewModel.OperationMessage = $"Failed to load current status: {ex.Message}";
        }
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
                LogDirectory = "../logs",
            },
        };
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

    private async void RefreshStatusButton_Click(object? sender, RoutedEventArgs e)
    {
        await LoadAsync();
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

        var fullPath = Path.IsPathRooted(logDirectory)
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
            if (File.Exists(tempConfigPath))
            {
                File.Delete(tempConfigPath);
            }
        }
    }
}
