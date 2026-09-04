using System.Windows.Input;
using ImmichFolderWatch.App.Linux.Platform;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.App.Linux.ViewModels;

public sealed class ShellViewModel : BindableBase
{
    private readonly INotifier _notifier;
    private readonly PortalFolderPicker _folderPicker;
    private readonly IThemeProvider _theme;
    private string _pickedFolderPath = string.Empty;
    private string _trayStatusText = "Tray status pending probe";

    public ShellViewModel(
        IPlatformPaths paths,
        INotifier notifier,
        IThemeProvider theme,
        PortalFolderPicker folderPicker,
        AvaloniaTrayHost trayHost)
    {
        ArgumentNullException.ThrowIfNull(paths);
        ArgumentNullException.ThrowIfNull(notifier);
        ArgumentNullException.ThrowIfNull(theme);
        ArgumentNullException.ThrowIfNull(folderPicker);
        ArgumentNullException.ThrowIfNull(trayHost);

        _notifier = notifier;
        _folderPicker = folderPicker;
        _theme = theme;

        VersionText = $"v{ProductVersionProvider.GetProductVersion(typeof(ShellViewModel).Assembly)?.ToString(3) ?? "unknown"}";
        ConfigPath = $"Config: {paths.GetConfigPath()}";
        LogDirectory = $"Logs:   {paths.GetLogDirectory()}";

        PickFolderCommand = new ActionCommand(PickFolderAsync);
        ShowNotificationCommand = new ActionCommand(ShowNotificationAsync);

        trayHost.TrayUnavailable += (_, _) => TrayStatusText =
            "Tray unavailable — running window-only (install the AppIndicator extension on GNOME for a tray icon).";
    }

    public string VersionText { get; }

    public string ConfigPath { get; }

    public string LogDirectory { get; }

    public ICommand PickFolderCommand { get; }

    public ICommand ShowNotificationCommand { get; }

    public string PickedFolderPath
    {
        get => _pickedFolderPath;
        private set => SetProperty(ref _pickedFolderPath, value);
    }

    public string TrayStatusText
    {
        get => _trayStatusText;
        private set => SetProperty(ref _trayStatusText, value);
    }

    public bool IsDarkTheme => _theme.IsDark;

    private async Task PickFolderAsync()
    {
        var picked = await _folderPicker.PickFolderAsync("Pick a folder to watch");
        if (!string.IsNullOrEmpty(picked))
        {
            PickedFolderPath = picked;
        }
    }

    private async Task ShowNotificationAsync()
    {
        await _notifier.ShowAsync(
            "Immich Folder Watch",
            "Hello from the Linux scaffold — D-Bus reachable.",
            NotificationKind.Info);
    }

    private sealed class ActionCommand : ICommand
    {
        private readonly Func<Task> _execute;

        public ActionCommand(Func<Task> execute)
        {
            _execute = execute;
        }

        public event EventHandler? CanExecuteChanged
        {
            add { }
            remove { }
        }

        public bool CanExecute(object? parameter) => true;

        public async void Execute(object? parameter) => await _execute().ConfigureAwait(false);
    }
}
