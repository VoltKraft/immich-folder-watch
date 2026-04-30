using System.Diagnostics;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Threading;
using ImmichFolderWatch.App.Linux.Hosting;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.DependencyInjection;

namespace ImmichFolderWatch.App.Linux.Views;

public sealed partial class MainWindow : Window
{
    private bool _initialLoadDone;
    private bool _isVerifyInProgress;
    private bool _isSaveInProgress;

    private MainWindowViewModel? ViewModel => DataContext as MainWindowViewModel;

    public MainWindow()
    {
        InitializeComponent();
        Opened += OnOpened;
    }

    private async void OnOpened(object? sender, EventArgs e)
    {
        if (_initialLoadDone)
        {
            return;
        }
        _initialLoadDone = true;

        var services = App.Services;
        if (services is null || ViewModel is null)
        {
            return;
        }

        var paths = services.GetRequiredService<IPlatformPaths>();
        var loader = services.GetRequiredService<AppConfigLoader>();
        var configPath = paths.GetConfigPath();

        AppConfig? loadedConfig = null;
        if (File.Exists(configPath))
        {
            try
            {
                loadedConfig = loader.LoadForEditing(configPath);
                ViewModel.Load(loadedConfig);
            }
            catch (Exception ex)
            {
                ViewModel.OperationMessage =
                    string.Format(System.Globalization.CultureInfo.CurrentCulture,
                        Strings_Op_ConfigLoadFailedFormat, ex.Message);
            }
        }

        if (loadedConfig is not null)
        {
            try
            {
                var runtimeConfig = AppConfigLoader.NormalizeForRuntime(
                    loadedConfig,
                    Path.GetDirectoryName(configPath) ?? AppContext.BaseDirectory);
                var host = services.GetRequiredService<AppHost>();
                await host.StartAsync(runtimeConfig);
            }
            catch
            {
                // Hosted-services start failure is non-fatal at this stage —
                // the user can fix the config + Save & Apply to retry.
            }
        }
    }

    private void ToggleApiKeyVisibilityButton_Click(object? sender, RoutedEventArgs e)
    {
        ViewModel?.ToggleImmichApiKeyVisibility();
    }

    private async void VerifyImmichButton_Click(object? sender, RoutedEventArgs e)
    {
        if (_isVerifyInProgress || ViewModel is null || App.Services is null)
        {
            return;
        }
        _isVerifyInProgress = true;

        try
        {
            ViewModel.SetImmichCheckInProgress();

            var paths = App.Services.GetRequiredService<IPlatformPaths>();
            var runner = App.Services.GetRequiredService<ConfigVerificationRunner>();
            var checkConfig = ViewModel.CreateImmichCheckConfig();

            var result = await runner.CheckImmichAccessAsync(
                checkConfig,
                paths.GetConfigPath(),
                CancellationToken.None);

            ViewModel.ApplyImmichCheckResult(result);
        }
        catch (Exception ex)
        {
            ViewModel.OperationMessage =
                string.Format(System.Globalization.CultureInfo.CurrentCulture,
                    Strings_Op_ImmichCheckFailedFormat, ex.Message);
        }
        finally
        {
            _isVerifyInProgress = false;
        }
    }

    private void AddSourceButton_Click(object? sender, RoutedEventArgs e)
    {
        ViewModel?.AddSource();
    }

    private void RemoveSourceButton_Click(object? sender, RoutedEventArgs e)
    {
        if (sender is Button button
            && button.DataContext is ImmichFolderWatch.App.Shared.Models.WatchSourceItem item
            && ViewModel is { } vm)
        {
            vm.Sources.Remove(item);
        }
    }

    private void UseDefaultLogDirectoryButton_Click(object? sender, RoutedEventArgs e)
    {
        if (App.Services is null || ViewModel is null)
        {
            return;
        }
        var paths = App.Services.GetRequiredService<IPlatformPaths>();
        ViewModel.LogDirectory = paths.GetLogDirectory();
    }

    private void OpenLogsButton_Click(object? sender, RoutedEventArgs e)
    {
        if (ViewModel is null)
        {
            return;
        }

        var dir = ViewModel.GetEffectiveLogDirectory();
        if (string.IsNullOrWhiteSpace(dir))
        {
            return;
        }

        try
        {
            Directory.CreateDirectory(dir);
            Process.Start(new ProcessStartInfo("xdg-open", dir)
            {
                UseShellExecute = false,
            });
        }
        catch (Exception ex)
        {
            ViewModel.OperationMessage = ex.Message;
        }
    }

    private async void SaveActionButton_Click(object? sender, RoutedEventArgs e)
    {
        if (_isSaveInProgress || ViewModel is null || App.Services is null)
        {
            return;
        }
        _isSaveInProgress = true;

        try
        {
            if (!ViewModel.TryCreateConfig(out var newConfig, out var errors))
            {
                ViewModel.OperationMessage = string.Join(Environment.NewLine, errors);
                return;
            }

            var paths = App.Services.GetRequiredService<IPlatformPaths>();
            var loader = App.Services.GetRequiredService<AppConfigLoader>();
            var configPath = paths.GetConfigPath();

            var configDir = Path.GetDirectoryName(configPath);
            if (!string.IsNullOrWhiteSpace(configDir))
            {
                Directory.CreateDirectory(configDir);
            }

            // The loader saves verbatim; runtime normalisation is applied
            // separately when handing the config to AppHost.
            await SaveYamlAsync(loader, newConfig, configPath);

            var runtimeConfig = AppConfigLoader.NormalizeForRuntime(
                newConfig,
                Path.GetDirectoryName(configPath) ?? AppContext.BaseDirectory);

            var host = App.Services.GetRequiredService<AppHost>();
            await host.RestartAsync(runtimeConfig);

            ViewModel.OperationMessage = Strings_Op_SavedApplied;
        }
        catch (Exception ex)
        {
            ViewModel.OperationMessage =
                string.Format(System.Globalization.CultureInfo.CurrentCulture,
                    Strings_Op_SaveFailedFormat, ex.Message);
        }
        finally
        {
            _isSaveInProgress = false;
        }
    }

    private static Task SaveYamlAsync(AppConfigLoader loader, AppConfig config, string path)
    {
        return Task.Run(() =>
        {
            var serializer = new YamlDotNet.Serialization.SerializerBuilder()
                .WithNamingConvention(YamlDotNet.Serialization.NamingConventions.CamelCaseNamingConvention.Instance)
                .Build();
            var yaml = serializer.Serialize(config);
            File.WriteAllText(path, yaml);
        });
    }

    private static string Strings_Op_ConfigLoadFailedFormat
        => ImmichFolderWatch.App.Shared.Resources.Strings.Op_ConfigLoadFailedFormat;
    private static string Strings_Op_ImmichCheckFailedFormat
        => ImmichFolderWatch.App.Shared.Resources.Strings.Op_ImmichCheckFailedFormat;
    private static string Strings_Op_SavedApplied
        => ImmichFolderWatch.App.Shared.Resources.Strings.Op_SavedApplied;
    private static string Strings_Op_SaveFailedFormat
        => ImmichFolderWatch.App.Shared.Resources.Strings.Op_SaveFailedFormat;
}
