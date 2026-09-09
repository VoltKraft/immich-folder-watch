using Avalonia;
using Avalonia.Automation;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Interactivity;
using Avalonia.LogicalTree;
using Avalonia.Media.Imaging;
using Avalonia.Styling;
using Avalonia.Threading;
using Avalonia.VisualTree;
using ImmichFolderWatch.App.Linux.Controls;
using ImmichFolderWatch.App.Linux.Views;
using ImmichFolderWatch.App.Shared.Models;
using ImmichFolderWatch.App.Shared.Resources;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

public sealed class MainWindowBindingTests
{
    [AvaloniaFact]
    public void NavigationAndSelectedSourceEditor_PreserveDraftEditsAcrossPages()
    {
        WithWindow((window, vm) =>
        {
            var navigation = window.FindControl<ListBox>("NavigationList")!;
            var sources = window.FindControl<ListBox>("SourcesList")!;
            var first = vm.SelectedSource!;
            vm.AddSource();
            var second = vm.SelectedSource!;
            second.Path = "/home/example/Pictures/Camera";
            second.AlbumName = "Camera";
            Flush(window);
            Assert.Equal(1, navigation.SelectedIndex);
            Assert.Same(second, sources.SelectedItem);

            sources.SelectedItem = first;
            Flush(window);
            var album = FindEditor<TextBox>(window, Strings.UI_ImmichAlbumName);
            album.SetCurrentValue(TextBox.TextProperty, "Edited album");
            Flush(window);
            Assert.Equal("Edited album", first.AlbumName);

            navigation.SelectedIndex = 3;
            Flush(window);
            Assert.True(vm.IsSettingsSelected);
            navigation.SelectedIndex = 1;
            sources.SelectedItem = second;
            Flush(window);
            Assert.Equal("Camera", album.Text);
            sources.SelectedItem = first;
            Flush(window);
            Assert.Equal("Edited album", album.Text);

            var tabs = window.FindControl<TabControl>("SourceEditorTabs")!;
            tabs.SelectedIndex = 1;
            Flush(window);
            FindEditor<TextBox>(window, Strings.UI_Extensions)
                .SetCurrentValue(TextBox.TextProperty, ".jpg\n.png");
            Flush(window);
            Assert.Equal(".jpg\n.png", first.ExtensionsText);
            window.GetVisualDescendants().OfType<Button>()
                .Single(button => Equals(button.Content, Strings.UI_Remove))
                .RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            Flush(window);
            Assert.Equal(0, tabs.SelectedIndex);
            Assert.Same(second, sources.SelectedItem);
            Assert.Equal("Camera", second.AlbumName);
            window.GetVisualDescendants().OfType<Button>()
                .Single(button => Equals(button.Content, Strings.UI_Remove))
                .RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            Flush(window);
            Assert.Empty(vm.Sources);
            Assert.Null(sources.SelectedItem);
            Assert.False(vm.HasSelectedSource);
            vm.AddSource();
            Flush(window);
            Assert.Same(Assert.Single(vm.Sources), sources.SelectedItem);
        });
    }

    [AvaloniaFact]
    public void SyncMode_HidesAdvancedTabAndMovesSelectionBackToGeneral()
    {
        WithWindow((window, vm) =>
        {
            vm.SelectedSectionIndex = 1;
            Flush(window);
            var tabs = window.FindControl<TabControl>("SourceEditorTabs")!;
            var advanced = Assert.IsType<TabItem>(tabs.Items[2]);
            Assert.True(advanced.IsVisible);
            var modes = FindEditor<ComboBox>(window, Strings.UI_SyncMode);
            tabs.SelectedIndex = 2;
            Flush(window);
            modes.SelectedItem = vm.AvailableSyncModes.Single(mode => mode.Code == WatchSourceSyncModes.Sync);
            Flush(window);
            Assert.Equal(WatchSourceSyncModes.Sync, vm.SelectedSource!.SyncMode);
            Assert.False(advanced.IsVisible);
            Assert.Equal(0, tabs.SelectedIndex);

            modes.SelectedItem = vm.AvailableSyncModes.Single(mode => mode.Code == WatchSourceSyncModes.UploadAll);
            Flush(window);
            Assert.True(advanced.IsVisible);
            Assert.Equal(WatchSourceSyncModes.UploadAll, vm.SelectedSource.SyncMode);
        });
    }

    [AvaloniaFact]
    public void ApiKey_IsMaskedAndRevealButtonUpdatesActualInput()
    {
        WithWindow((window, vm) =>
        {
            vm.SelectedSectionIndex = 2;
            vm.ImmichApiKey = "SYNTHETIC_TEST_KEY";
            Flush(window);
            var input = window.FindControl<TextBox>("ApiKeyInput")!;
            Assert.Equal('•', input.PasswordChar);
            Assert.False(input.RevealPassword);
            Assert.Equal(vm.ImmichApiKey, input.Text);
            var reveal = FindEditor<Button>(window, vm.ImmichApiKeyRevealToolTip);
            reveal.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            Flush(window);
            Assert.True(input.RevealPassword);
            reveal.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            Flush(window);
            Assert.False(input.RevealPassword);
        });
    }

    [AvaloniaFact]
    public void PortalPath_DisplaysHostFolderWithoutEditingTheGrantedAccessPath()
    {
        WithWindow((window, vm) =>
        {
            const string grantedPath = "/run/user/1000/doc/example/photos";
            const string hostPath = "/home/example/Pictures/Photos";
            vm.SelectedSource!.SetPortalPath(grantedPath, hostPath);
            vm.SelectedSectionIndex = 1;
            Flush(window);
            var pathInput = window.FindControl<TextBox>("SourcePathInput")!;
            Assert.True(pathInput.IsReadOnly);
            Assert.Equal(hostPath, pathInput.Text);
            Assert.True(vm.TryCreateConfig(out var config, out _));
            Assert.Equal(grantedPath, Assert.Single(config.Watch.Sources).Path);
        });
    }

    [AvaloniaFact]
    public void StatusPills_TrackCheckResultsAndRefreshColorsWhenThemeChanges()
    {
        WithWindow((window, vm) =>
        {
            vm.SelectedSectionIndex = 2;
            vm.ApplyImmichCheckResult(new ImmichAccessCheckResult
            {
                UrlState = CheckState.Failed,
                ApiKeyState = CheckState.Passed,
                PermissionsState = CheckState.Warning,
                PermissionResults =
                [
                    new ImmichPermissionCheckResult
                    {
                        PermissionName = "asset.upload",
                        DisplayName = "Asset upload",
                        State = CheckState.Warning,
                        Message = "Synthetic warning for the UI test.",
                    },
                ],
            });
            Flush(window);
            var pills = window.GetLogicalDescendants().OfType<StatusPill>().ToList();
            Assert.Contains(pills, pill => pill.Tone == StatusTone.Error && pill.Text == vm.ImmichUrlStatusText);
            Assert.Contains(pills, pill => pill.Tone == StatusTone.Success && pill.Text == vm.ImmichApiKeyStatusText);
            Assert.Contains(pills, pill => pill.Tone == StatusTone.Warning && pill.Text == vm.ImmichPermissionsStatusText);

            var error = pills.First(pill => pill.Tone == StatusTone.Error);
            window.RequestedThemeVariant = ThemeVariant.Light;
            Flush(window);
            var light = error.Background?.ToString();
            window.RequestedThemeVariant = ThemeVariant.Dark;
            Flush(window);
            Assert.NotNull(light);
            Assert.NotEqual(light, error.Background?.ToString());

            vm.SetImmichCheckInProgress();
            Flush(window);
            Assert.Equal(StatusTone.Info, error.Tone);
            Assert.Equal(vm.ImmichUrlStatusText, error.Text);
        });
    }

    [AvaloniaFact]
    public void CloseButton_HidesWindowAndAllowsReopening()
    {
        WithWindow((window, _) =>
        {
            Assert.True(window.IsVisible);
            window.Close();
            Assert.False(window.IsVisible);
            window.Show();
            Flush(window);
            Assert.True(window.IsVisible);
        });
    }

    [AvaloniaFact]
    public void ExplicitShutdown_ClosesWindowInsteadOfCancelingExit()
    {
        WithWindow((window, _) =>
        {
            var closed = false;
            window.Closed += (_, _) => closed = true;
            window.IsExiting = true;
            window.Close();
            Assert.True(closed);
            Assert.False(window.IsVisible);
        });
    }

    [AvaloniaFact]
    public void MainPages_RenderAtMinimumSize_AndExportSyntheticPreviewsWhenRequested()
    {
        WithWindow((window, vm) =>
        {
            var sourceTabs = window.FindControl<TabControl>("SourceEditorTabs")!;
            var settingsTabs = window.GetLogicalDescendants().OfType<TabControl>()
                .Single(tabs => tabs != sourceTabs);
            vm.LoggingTarget = LogTargets.File;
            vm.LogDirectory = "/home/example/.local/state/immich-folder-watch/logs";
            var outputDirectory = Environment.GetEnvironmentVariable("IFW_UI_PREVIEW_DIRECTORY");
            var pages = new (string Name, int Section, int Tab)[]
            {
                ("overview", 0, 0), ("folders", 1, 0), ("filters", 1, 1),
                ("advanced", 1, 2), ("connection", 2, 0),
                ("settings", 3, 0), ("transfer", 3, 1), ("logging", 3, 2),
            };
            foreach (var theme in new[] { ThemeVariant.Light, ThemeVariant.Dark })
            {
                window.RequestedThemeVariant = theme;
                foreach (var page in pages)
                {
                    vm.SelectedSectionIndex = page.Section;
                    sourceTabs.SelectedIndex = page.Section == 1 ? page.Tab : 0;
                    settingsTabs.SelectedIndex = page.Section == 3 ? page.Tab : 0;
                    window.Width = window.MinWidth;
                    window.Height = window.MinHeight;
                    Flush(window);
                    var saveButton = window.GetVisualDescendants().OfType<Button>()
                        .Single(button => Equals(button.Content, vm.SaveActionButtonText));
                    var origin = saveButton.TranslatePoint(default, window);
                    Assert.NotNull(origin);
                    Assert.True(origin.Value.Y >= 0);
                    Assert.True(origin.Value.Y + saveButton.Bounds.Height <= window.Bounds.Height);

                    if (!string.IsNullOrWhiteSpace(outputDirectory))
                    {
                        Directory.CreateDirectory(outputDirectory);
                        window.Width = 1080;
                        window.Height = 800;
                        Flush(window);
                        using var bitmap = new RenderTargetBitmap(new PixelSize(1080, 800));
                        bitmap.Render(window);
                        bitmap.Save(Path.Combine(outputDirectory, $"linux-{theme.Key.ToString()!.ToLowerInvariant()}-{page.Name}.png"));
                    }
                }
            }
        });
    }

    private static T FindEditor<T>(MainWindow window, string label) where T : Control =>
        window.GetVisualDescendants().OfType<T>()
            .Single(control => AutomationProperties.GetName(control) == label);

    private static void Flush(MainWindow window)
    {
        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();
        Dispatcher.UIThread.RunJobs();
    }

    private static void WithWindow(Action<MainWindow, MainWindowViewModel> verify)
    {
        // Never initialize the production App: its services start network, portal,
        // startup and filesystem integrations. The real view runs with synthetic data.
        Assert.Null(ImmichFolderWatch.App.Linux.App.Services);
        LocalizationService.Instance.SetLanguage(LocalizationService.LanguageEnglish);
        var vm = new MainWindowViewModel(new SyncStatusProvider(), new TestAutostartManager(),
            LocalizationService.Instance, new TestDispatcher(), new LinuxLoggingCapabilities())
        {
            ProductVersionText = "Preview · sample data",
            ImmichServerApiUrl = "https://immich.example.com/api",
        };
        vm.SelectedSource!.Path = "/home/example/Pictures/Screenshots";
        vm.SelectedSource.AlbumName = "Screenshots";
        vm.SelectedSource.IncludeSubdirectories = true;
        vm.SelectedSource.ExtensionsText = ".jpg\n.png\n.heic\n.mp4";
        vm.SelectedSource.ExcludeDirectoriesText = "private";
        vm.SelectedSource.ExcludeFileNamesText = "Thumbs.db";
        var window = new MainWindow { DataContext = vm };
        try
        {
            window.Show();
            Flush(window);
            verify(window, vm);
        }
        finally
        {
            window.Hide();
            window.DataContext = null;
            LocalizationService.Instance.SetLanguage(LocalizationService.LanguageAuto);
        }
    }

    private sealed class TestAutostartManager : IAutoStartManager
    {
        public Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default) => Task.FromResult(false);
        public Task EnableAsync(CancellationToken cancellationToken = default) => throw new InvalidOperationException("No startup changes in UI tests.");
        public Task DisableAsync(CancellationToken cancellationToken = default) => throw new InvalidOperationException("No startup changes in UI tests.");
    }

    private sealed class TestDispatcher : IUiDispatcher
    {
        public bool IsOnUiThread => Dispatcher.UIThread.CheckAccess();
        public void Post(Action action) => Dispatcher.UIThread.Post(action);
    }
}
