using System.Diagnostics;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using ImmichFolderWatch.App.Linux.Hosting;
using ImmichFolderWatch.App.Linux.Logging;
using ImmichFolderWatch.App.Linux.Services;
using ImmichFolderWatch.App.Linux.Platform;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.Resources;
using ImmichFolderWatch.App.Shared.Models;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.App.Linux.Views;

public sealed partial class MainWindow : Window
{
    private Task? _bootstrapTask;
    private Task? _backgroundRequestTask;
    private LogsWindow? _logsWindow;
    internal bool IsExiting { get; set; }
    private readonly ImmichAccessCheckSession _accessChecks = new();
    private bool _isSaveInProgress;

    private MainWindowViewModel? ViewModel => DataContext as MainWindowViewModel;

    public MainWindow()
    {
        InitializeComponent();
        Opened += OnOpened;
        Closed += (_, _) => _accessChecks.Dispose();
    }

    protected override void OnClosing(WindowClosingEventArgs e)
    {
        base.OnClosing(e);
        if (e.Cancel || IsExiting)
        {
            return;
        }

        // Always hide on close: the FolderWatchWorker keeps running in
        // the background. Re-open paths:
        // - System tray icon where enabled outside the Flatpak sandbox.
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
            _backgroundRequestTask ??= bgClient.RequestBackgroundAsync(App.ShutdownToken);
        }
    }

    private async void QuitButton_Click(object? sender, RoutedEventArgs e)
    {
        if (Application.Current is App app)
        {
            await app.ShutdownAsync();
        }
    }

    private void UpdateHyperlinkButton_Click(object? sender, RoutedEventArgs e)
    {
        var downloadUri = ViewModel?.UpdateDownloadUri;
        if (downloadUri is null)
        {
            return;
        }

        var logger = App.Services?.GetService<ILogger<MainWindow>>();
        try
        {
            var process = Process.Start(new ProcessStartInfo("xdg-open", downloadUri.AbsoluteUri)
            {
                UseShellExecute = false,
            });
            if (process is null)
            {
                logger?.LogWarning("Could not start xdg-open for the update download page {UpdateDownloadUri}.", downloadUri);
            }
        }
        catch (Exception ex)
        {
            logger?.LogWarning(ex, "Could not open the update download page {UpdateDownloadUri}.", downloadUri);
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
            App.ShutdownToken.ThrowIfCancellationRequested();
            var hostPath = await docClient.ResolveHostPathAsync(source.Path, App.ShutdownToken);
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
    /// <see cref="_bootstrapTask"/> to keep both call sites idempotent.
    /// </summary>
    internal Task EnsureBootstrappedAsync() => _bootstrapTask ??= BootstrapAsync();

    internal Task WaitForBootstrapAsync() => Task.WhenAll(
        _bootstrapTask ?? Task.CompletedTask, _backgroundRequestTask ?? Task.CompletedTask);

    private async Task BootstrapAsync()
    {
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
                loadedConfig.Logging.LogDirectory = AppConfigLoader.NormalizeForRuntime(
                    loadedConfig, Path.GetDirectoryName(configPath) ?? AppContext.BaseDirectory).Logging.LogDirectory;
                ViewModel.Load(loadedConfig);
                await ResolveSourceDisplayPathsAsync(services);
            }
            catch (OperationCanceledException) when (App.ShutdownToken.IsCancellationRequested)
            {
                return;
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
                await host.StartAsync(runtimeConfig, App.ShutdownToken);
            }
            catch (OperationCanceledException) when (App.ShutdownToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception ex)
            {
                ViewModel.OperationMessage = string.Format(
                    System.Globalization.CultureInfo.CurrentCulture,
                    Localized("Op_SyncStartFailedFormat"), ex.Message);
                services.GetRequiredService<ILogger<MainWindow>>().LogWarning(ex, "Could not start synchronization.");
            }
        }

        await Task.WhenAll(
            InitializeAutostartAsync(configPath),
            RunImmichAccessCheckAsync(updateOperationMessage: false));
    }

    private async Task InitializeAutostartAsync(string configPath)
    {
        if (App.Services is null || ViewModel is null)
        {
            return;
        }

        var manager = App.Services.GetRequiredService<PortalAutostartManager>();
        try
        {
            await ViewModel.InitializeAutostartAsync(
                ct => manager.InitializeAsync(File.Exists(configPath), ct), App.ShutdownToken);
        }
        catch (OperationCanceledException) when (App.ShutdownToken.IsCancellationRequested)
        {
        }
    }

    private void ToggleApiKeyVisibilityButton_Click(object? sender, RoutedEventArgs e)
    {
        ViewModel?.ToggleImmichApiKeyVisibility();
    }

    private async void VerifyImmichButton_Click(object? sender, RoutedEventArgs e)
    {
        await RunImmichAccessCheckAsync(updateOperationMessage: true);
    }

    private Task RunImmichAccessCheckAsync(bool updateOperationMessage)
    {
        if (_isSaveInProgress || ViewModel is null || App.Services is null)
        {
            return Task.CompletedTask;
        }
        var checkConfig = ViewModel.CreateImmichCheckConfig();
        ViewModel.SetImmichCheckInProgress();
        if (updateOperationMessage)
        {
            ViewModel.OperationMessage = Strings.Op_CheckingImmich;
        }
        var paths = App.Services.GetRequiredService<IPlatformPaths>();
        var runner = App.Services.GetRequiredService<ConfigVerificationRunner>();
        return _accessChecks.RunAsync(checkConfig,
            (config, token) => runner.CheckImmichAccessAsync(config, paths.GetConfigPath(), token),
            result =>
            {
                if (!CheckStillMatchesDraft(checkConfig)) return;
                ViewModel.ApplyImmichCheckResult(result);
                if (updateOperationMessage)
                {
                    ViewModel.OperationMessage = BuildImmichCheckSummary(result);
                }
            },
            exception =>
            {
                if (!CheckStillMatchesDraft(checkConfig)) return;
                ViewModel.ApplyImmichCheckResult(ConfigVerificationRunner.CreateUnexpectedFailureResult(exception, checkConfig));
                ViewModel.OperationMessage = string.Format(System.Globalization.CultureInfo.CurrentCulture,
                    Strings.Op_ImmichCheckFailedFormat, exception.Message);
            },
            App.ShutdownToken);
    }

    private bool CheckStillMatchesDraft(AppConfig checkedConfig)
    {
        if (ViewModel is null) return false;
        var current = ViewModel.CreateImmichCheckConfig();
        static (bool Albums, bool Sync) RequiredPermissions(AppConfig config) => (
            config.Watch.Sources.Any(source => !string.IsNullOrWhiteSpace(source.AlbumName)),
            config.Watch.Sources.Any(source => WatchSourceSyncModes.Normalize(source.SyncMode) == WatchSourceSyncModes.Sync));
        if (checkedConfig.Immich.ServerApiUrl == current.Immich.ServerApiUrl
            && checkedConfig.Immich.ApiKey == current.Immich.ApiKey
            && RequiredPermissions(checkedConfig) == RequiredPermissions(current))
        {
            return true;
        }
        ViewModel.ResetImmichCheckStatus();
        if (ViewModel.OperationMessage == Strings.Op_CheckingImmich)
        {
            ViewModel.OperationMessage = string.Empty;
        }
        return false;
    }

    private static string BuildImmichCheckSummary(ImmichAccessCheckResult result)
    {
        if (result.UrlState == CheckState.Failed)
        {
            return result.UrlMessage;
        }
        if (result.ApiKeyState == CheckState.Failed)
        {
            return result.ApiKeyMessage;
        }
        return result.PermissionsState switch
        {
            CheckState.Passed => Strings.Op_ImmichCheckOk,
            CheckState.Warning or CheckState.Failed => result.PermissionsMessage,
            _ => Strings.Op_ImmichCheckDone,
        };
    }

    private async void AddSourceButton_Click(object? sender, RoutedEventArgs e)
    {
        if (App.Services is null || ViewModel is null)
        {
            return;
        }

        var picker = App.Services.GetRequiredService<PortalFolderPicker>();
        var picked = await picker.PickFolderAsync(Localized("UI_ChooseFolder"));
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

    private async void ChangeSourceFolderButton_Click(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { DataContext: WatchSourceItem source } || App.Services is null)
        {
            return;
        }
        var picker = App.Services.GetRequiredService<PortalFolderPicker>();
        var picked = await picker.PickFolderAsync(Localized("UI_ChooseFolder"));
        if (string.IsNullOrWhiteSpace(picked))
        {
            return;
        }
        var docClient = App.Services.GetRequiredService<DocumentPortalClient>();
        var hostPath = await docClient.ResolveHostPathAsync(picked);
        source.SetPortalPath(picked, hostPath ?? picked);
    }

    private void ManageSourcesButton_Click(object? sender, RoutedEventArgs e)
    {
        if (ViewModel is { } vm)
        {
            vm.SelectedSectionIndex = 1;
        }
    }

    private void SourceEditor_DataContextChanged(object? sender, EventArgs e)
    {
        // A newly selected sync source may hide the previously selected Advanced tab.
        if (sender is TabControl tabs)
        {
            tabs.SelectedIndex = 0;
        }
    }

    private void AdvancedOptionsTab_PropertyChanged(object? sender, AvaloniaPropertyChangedEventArgs e)
    {
        // Mode changes can also hide Advanced without replacing the selected source.
        if (e.Property == IsVisibleProperty
            && sender is TabItem { IsVisible: false }
            && this.FindControl<TabControl>("SourceEditorTabs") is { SelectedIndex: 2 } tabs)
        {
            tabs.SelectedIndex = 0;
        }
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
        ViewModel.OperationMessage = Strings.Op_LogDirReset;
    }

    private void OpenLogsButton_Click(object? sender, RoutedEventArgs e)
    {
        if (ViewModel is null)
        {
            return;
        }

        if (LogTargets.IsJournald(ViewModel.LoggingTarget) && App.Services is not null)
        {
            if (_logsWindow is null)
            {
                _logsWindow = new LogsWindow(App.Services.GetRequiredService<SessionLogBuffer>());
                _logsWindow.Closed += (_, _) => _logsWindow = null;
                _logsWindow.Show(this);
            }
            _logsWindow.Activate();
            return;
        }

        var dir = ViewModel.GetEffectiveLogDirectory();
        if (string.IsNullOrWhiteSpace(dir))
        {
            ViewModel.OperationMessage =
                Strings.Op_NoLogDir;
            return;
        }

        try
        {
            if (!Path.IsPathFullyQualified(dir) && App.Services is not null)
            {
                var configPath = App.Services.GetRequiredService<IPlatformPaths>().GetConfigPath();
                dir = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(configPath)!, dir));
            }
            if (!Directory.Exists(dir))
            {
                ViewModel.OperationMessage = string.Format(System.Globalization.CultureInfo.CurrentCulture,
                    Strings.Op_LogDirMissingFormat, dir);
                return;
            }
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
        if (!ViewModel.TryCreateConfig(out var draftConfig, out var errors))
        {
            ViewModel.OperationMessage = string.Join(Environment.NewLine, errors);
            return;
        }
        _accessChecks.Cancel();
        ViewModel.ResetImmichCheckStatus();
        _isSaveInProgress = true;
        var mainContent = this.FindControl<Control>("MainContent");
        if (mainContent is not null) mainContent.IsEnabled = false;
        try
        {
            ViewModel.OperationMessage = Strings.Op_CheckingConfig;
            var paths = App.Services.GetRequiredService<IPlatformPaths>();
            var host = App.Services.GetRequiredService<AppHost>();
            var result = await App.Services.GetRequiredService<ConfigApplyService>().ApplyAsync(
                draftConfig, paths.GetConfigPath(), host.RestartAsync,
                accessChecked: ViewModel.ApplyImmichCheckResult,
                saving: () => ViewModel.OperationMessage = Strings.Op_SavingRestarting,
                cancellationToken: App.ShutdownToken);
            if (!result.Success)
            {
                ViewModel.OperationMessage = string.Join(Environment.NewLine, result.Errors);
                return;
            }
            var loader = App.Services.GetRequiredService<AppConfigLoader>();
            ViewModel.Load(loader.LoadForEditing(paths.GetConfigPath()), resetImmichCheckStatus: false);
            await ResolveSourceDisplayPathsAsync(App.Services);
            ViewModel.OperationMessage = string.IsNullOrWhiteSpace(host.LastLoggingWarning)
                ? Strings.Op_SavedApplied
                : $"{Strings.Op_SavedApplied} — {host.LastLoggingWarning}";
        }
        catch (OperationCanceledException) when (App.ShutdownToken.IsCancellationRequested)
        {
        }
        catch (Exception ex)
        {
            ViewModel.OperationMessage = string.Format(System.Globalization.CultureInfo.CurrentCulture,
                Strings.Op_SaveFailedFormat, ex.Message);
        }
        finally
        {
            _isSaveInProgress = false;
            if (mainContent is not null) mainContent.IsEnabled = true;
        }
    }

    private static string Localized(string key) => Strings.ResourceManager.GetString(key, Strings.Culture) ?? key;

    private static string Strings_Op_ConfigLoadFailedFormat => Strings.Op_ConfigLoadFailedFormat;
}
