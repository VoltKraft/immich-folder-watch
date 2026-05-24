using System.Diagnostics;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Interactivity;
using Avalonia.Threading;
using ImmichFolderWatch.App.Linux.Hosting;
using ImmichFolderWatch.App.Linux.Platform;
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

    protected override void OnClosing(WindowClosingEventArgs e)
    {
        base.OnClosing(e);
        if (e.Cancel)
        {
            return;
        }

        // Always hide on close: the FolderWatchWorker keeps running in
        // the background. Re-open paths:
        // - System tray icon where enabled outside the Flathub sandbox.
        // - Click the .desktop launcher again — UnixSingleInstance
        //   Coordinator catches the second-instance signal and shows
        //   the window.
        // - GNOME 46+ Background Apps panel (Quick Settings) once
        //   BackgroundPortalClient.RequestBackgroundAsync has confirmed
        //   our background-mode opt-in.
        // The footer Quit button (and the tray Quit menu item where
        // available outside Flatpak) is the explicit exit path.
        e.Cancel = true;
        Hide();

        // Lazy: ask the Background portal for permission the first time
        // the window is hidden. Fire-and-forget — RequestBackground
        // surfaces a one-time GNOME dialog; later hides see the cached
        // grant and no-op. KDE / non-portal sessions get a silent
        // fallback inside the client.
        var bgClient = App.Services?.GetService<BackgroundPortalClient>();
        if (bgClient is not null)
        {
            _ = bgClient.RequestBackgroundAsync();
        }
    }

    private void QuitButton_Click(object? sender, RoutedEventArgs e)
    {
        if (Application.Current?.ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.Shutdown(0);
        }
    }

    private async Task ResolveSourceDisplayPathsAsync(IServiceProvider services)
    {
        if (ViewModel is null)
        {
            return;
        }

        var docClient = services.GetService<DocumentPortalClient>();
        if (docClient is null)
        {
            return;
        }

        // Walk a snapshot of the Sources collection so user-driven
        // mutations during the async resolves don't trip the iterator.
        var snapshot = ViewModel.Sources.ToList();
        foreach (var source in snapshot)
        {
            var hostPath = await docClient.ResolveHostPathAsync(source.Path);
            if (!string.IsNullOrEmpty(hostPath))
            {
                source.SetPortalPath(source.Path, hostPath);
            }
        }
    }

    private async void OnOpened(object? sender, EventArgs e)
    {
        await EnsureBootstrappedAsync();
    }

    /// <summary>
    /// Runs the initial config load + AppHost start exactly once, regardless
    /// of whether the window has ever been shown. Called from
    /// <see cref="OnOpened"/> on the first window open AND directly from
    /// <see cref="App.OnFrameworkInitializationCompleted"/> when the app
    /// launches with --background (autostart): in that path the window
    /// stays hidden, so the Opened event never fires and the
    /// FolderWatchWorker would otherwise never start. Guarded by
    /// <see cref="_initialLoadDone"/> to keep both call sites idempotent.
    /// </summary>
    internal async Task EnsureBootstrappedAsync()
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
                await ResolveSourceDisplayPathsAsync(services);
            }
            catch (Exception ex)
            {
                ViewModel.OperationMessage =
                    string.Format(System.Globalization.CultureInfo.CurrentCulture,
                        Strings_Op_ConfigLoadFailedFormat, ex.Message);
            }
        }

        // Seed the log directory from IPlatformPaths when unset, so the
        // FileLogger writes somewhere the Open Logs button can resolve.
        // The platform-aware LoggingTarget default (Journald on Linux)
        // is set in the VM ctor + coerced by IPlatformLoggingCapabilities
        // when loading a stale YAML; nothing to force here anymore.
        if (string.IsNullOrWhiteSpace(ViewModel.LogDirectory))
        {
            ViewModel.LogDirectory = paths.GetLogDirectory();
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

    private async void AddSourceButton_Click(object? sender, RoutedEventArgs e)
    {
        if (App.Services is null || ViewModel is null)
        {
            return;
        }

        var picker = App.Services.GetRequiredService<PortalFolderPicker>();
        var picked = await picker.PickFolderAsync("Pick a folder to watch");
        if (string.IsNullOrWhiteSpace(picked))
        {
            // User dismissed the picker — do not append an empty source.
            return;
        }

        ViewModel.AddSource();
        var newItem = ViewModel.Sources[^1];

        // The picker hands us /run/user/$UID/doc/<token>/... — opaque
        // to the user but what the FolderWatchWorker has to read inside
        // the sandbox. Resolve the original host path via the Documents
        // portal so the TextBox can show "~/Pictures/Photos" instead.
        var docClient = App.Services.GetRequiredService<DocumentPortalClient>();
        var hostPath = await docClient.ResolveHostPathAsync(picked);
        newItem.SetPortalPath(picked, hostPath ?? picked);
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
            ViewModel.OperationMessage =
                "Log directory is empty (logging target may be set to a non-file target).";
            return;
        }

        try
        {
            Directory.CreateDirectory(dir);
            var proc = Process.Start(new ProcessStartInfo("xdg-open", dir)
            {
                UseShellExecute = false,
            });
            if (proc is null)
            {
                ViewModel.OperationMessage = $"Could not start xdg-open for {dir}.";
            }
        }
        catch (Exception ex)
        {
            ViewModel.OperationMessage = $"Open Logs failed: {ex.Message}";
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
