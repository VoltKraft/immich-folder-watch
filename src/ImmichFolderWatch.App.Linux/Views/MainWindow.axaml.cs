using Avalonia.Controls;
using Avalonia.Interactivity;
using ImmichFolderWatch.App.Linux.Platform;
using ImmichFolderWatch.App.Shared.ViewModels;

namespace ImmichFolderWatch.App.Linux.Views;

public sealed partial class MainWindow : Window
{
    private MainWindowViewModel? ViewModel => DataContext as MainWindowViewModel;

    public MainWindow()
    {
        InitializeComponent();
    }

    private void ToggleApiKeyVisibilityButton_Click(object? sender, RoutedEventArgs e)
    {
        ViewModel?.ToggleImmichApiKeyVisibility();
    }

    private void VerifyImmichButton_Click(object? sender, RoutedEventArgs e)
    {
        // 3.7.C — wires the actual ImmichAccessChecker run.
        ViewModel?.SetImmichCheckInProgress();
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
        // 3.7.C — populate with platform-default log directory from IPlatformPaths.
    }

    private void OpenLogsButton_Click(object? sender, RoutedEventArgs e)
    {
        // 3.7.C — xdg-open on the sandbox log path.
    }

    private void SaveActionButton_Click(object? sender, RoutedEventArgs e)
    {
        // 3.7.C — wires the AppConfig save + service restart.
    }
}
