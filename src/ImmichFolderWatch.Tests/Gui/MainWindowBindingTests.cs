using System.Runtime.ExceptionServices;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using ImmichFolderWatch.App;
using ImmichFolderWatch.App.Hosting;
using ImmichFolderWatch.App.Services;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Gui;

[Collection(nameof(WpfApplicationCollection))]
public sealed class MainWindowBindingTests
{
    private static void VerifyUpdateAvailableTextBinding(MainWindow window)
    {
        var run = Assert.IsType<Run>(window.FindName("UpdateAvailableTextRun"));
        var binding = BindingOperations.GetBinding(run, Run.TextProperty);
        Assert.NotNull(binding);
        Assert.Equal(BindingMode.OneWay, binding.Mode);
    }

    [Fact]
    public void NavigationAndSelectedSourceEditor_PreserveDraftEditsAcrossPages()
    {
        RunOnSta(() => WithWindow(window =>
        {
            VerifyUpdateAvailableTextBinding(window);
            var viewModel = Assert.IsType<MainWindowViewModel>(window.DataContext);
            var navigation = Assert.IsType<ListBox>(window.FindName("SectionNavigation"));
            var sourceList = Assert.IsType<ListBox>(window.FindName("SourceList"));
            var editor = Assert.IsType<Grid>(window.FindName("SourceEditor"));
            var tabs = Assert.IsType<TabControl>(window.FindName("SourceTabs"));
            var first = viewModel.Sources[0];
            first.Path = @"C:\Pictures\Screenshots";
            first.AlbumName = "Screenshots";
            viewModel.AddSource();
            var second = viewModel.Sources[1];
            second.Path = @"C:\Pictures\Camera";
            second.AlbumName = "Camera";
            FlushBindings();

            Assert.Equal(1, navigation.SelectedIndex);
            Assert.Same(second, sourceList.SelectedItem);
            Assert.Same(second, editor.DataContext);

            sourceList.SelectedItem = first;
            FlushBindings();
            Assert.Same(first, viewModel.SelectedSource);
            Assert.Same(first, editor.DataContext);
            var general = Assert.IsType<TabItem>(tabs.Items[0]);
            var album = FindBoundEditor<TextBox>(general.Content, TextBox.TextProperty, "AlbumName");
            album.SetCurrentValue(TextBox.TextProperty, "Edited album");
            album.GetBindingExpression(TextBox.TextProperty)!.UpdateSource();

            navigation.SelectedIndex = 3;
            FlushBindings();
            Assert.True(viewModel.IsSettingsSelected);
            Assert.Equal(Visibility.Collapsed, ((FrameworkElement)window.FindName("FoldersPage")).Visibility);
            Assert.Equal(Visibility.Visible, ((FrameworkElement)window.FindName("SettingsPage")).Visibility);
            navigation.SelectedIndex = 1;
            sourceList.SelectedItem = second;
            FlushBindings();
            Assert.Equal("Camera", album.Text);
            sourceList.SelectedItem = first;
            FlushBindings();
            Assert.Equal("Edited album", album.Text);

            tabs.SelectedIndex = 1;
            FlushBindings();
            var filters = Assert.IsType<TabItem>(tabs.Items[1]);
            var extensions = FindBoundEditor<TextBox>(filters.Content, TextBox.TextProperty, "ExtensionsText");
            extensions.SetCurrentValue(TextBox.TextProperty, ".jpg\n.png");
            extensions.GetBindingExpression(TextBox.TextProperty)!.UpdateSource();
            Assert.Equal(".jpg\n.png", first.ExtensionsText);

            viewModel.Sources.Remove(first);
            FlushBindings();
            Assert.Equal(0, tabs.SelectedIndex);
            Assert.Same(second, sourceList.SelectedItem);
            Assert.Same(second, editor.DataContext);
            Assert.Equal("Camera", second.AlbumName);

            VerifyEditableSettings(window, tabs);
            RenderPreviewWhenRequested(window, tabs);
            VerifyBoundedLayout(window);
        }));
    }

    private static void RunOnSta(Action check)
    {
        Exception? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                check();
            }
            catch (Exception ex)
            {
                failure = ex;
            }
            finally
            {
                Dispatcher.CurrentDispatcher.InvokeShutdown();
            }
        }) { IsBackground = true };
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(30)), "The WPF binding check timed out.");

        if (failure is not null)
        {
            ExceptionDispatchInfo.Capture(failure).Throw();
        }
    }

    private static void WithWindow(Action<MainWindow> verify)
    {
        var application = new Application
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown,
        };
        AppHost? appHost = null;
        MainWindow? window = null;
        try
        {
            application.Resources.MergedDictionaries.Add(new ResourceDictionary
            {
                Source = new Uri(
                    "pack://application:,,,/ImmichFolderWatch;component/Styles/PaletteDark.xaml",
                    UriKind.Absolute),
            });
            application.Resources.MergedDictionaries.Add(new ResourceDictionary
            {
                Source = new Uri(
                    "pack://application:,,,/ImmichFolderWatch;component/Styles/Styles.xaml",
                    UriKind.Absolute),
            });
            var localizationService = new LocalizationService();
            application.Resources["Loc"] = new LocalizationProxy(localizationService);

            var syncStatusProvider = new SyncStatusProvider();
            appHost = new AppHost(syncStatusProvider);
            window = new MainWindow(
                appHost,
                syncStatusProvider,
                new TestAutostartManager(),
                new AppConfigLoader(),
                new ThemeWatcher(application),
                localizationService,
                NullLogger<MainWindow>.Instance,
                "Test version");

            // Keep the window unshown: its Loaded handler reads the user's
            // configuration and starts access verification.
            Assert.False(window.IsLoaded);
            Assert.False(appHost.IsRunning);
            verify(window);
            // Virtualized source selection queues bring-into-view work. Complete it
            // while application resources are still available, before shutdown.
            application.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
            Assert.False(window.IsLoaded);
            Assert.False(appHost.IsRunning);
        }
        finally
        {
            try
            {
                window?.Close();
            }
            finally
            {
                try
                {
                    appHost?.DisposeAsync().AsTask().GetAwaiter().GetResult();
                }
                finally
                {
                    application.Shutdown();
                    // Shutdown queues its cleanup. Complete it before this STA
                    // exits so later tests do not see its global Application.
                    application.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
                    Assert.Null(Application.Current);
                }
            }
        }
    }

    private static void FlushBindings() =>
        Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.DataBind);

    private static void VerifyEditableSettings(MainWindow window, TabControl sourceTabs)
    {
        // These controls must remain reachable even when their page or tab is inactive.
        foreach (var path in new[] { "Path", "AlbumName", "ExtensionsText", "ExcludeDirectoriesText", "ExcludeFileNamesText" })
        {
            Assert.NotNull(FindBoundEditor<TextBox>(sourceTabs, TextBox.TextProperty, path));
        }

        foreach (var path in new[]
        {
            "ImmichServerApiUrl", "ImmichApiKey", "BatchIntervalSeconds", "MaxBatchSize",
            "FileReadyTimeoutSeconds", "RetryMaxAttempts", "RetryBaseDelayMilliseconds", "LogDirectory",
        })
        {
            Assert.NotNull(FindBoundEditor<TextBox>(window.Content, TextBox.TextProperty, path));
        }

        var viewModel = (MainWindowViewModel)window.DataContext;
        var source = viewModel.SelectedSource!;
        var include = FindBoundEditor<CheckBox>(sourceTabs, CheckBox.IsCheckedProperty, "IncludeSubdirectories");
        var delete = FindBoundEditor<CheckBox>(sourceTabs, CheckBox.IsCheckedProperty, "DeleteAfterUpload");
        source.SyncMode = WatchSourceSyncModes.Sync;
        FlushBindings();
        Assert.Equal(Visibility.Collapsed, include.Visibility);
        Assert.Equal(Visibility.Collapsed, delete.Visibility);
        Assert.Equal(Visibility.Collapsed, ((TabItem)sourceTabs.Items[2]).Visibility);
        source.SyncMode = WatchSourceSyncModes.UploadNew;
        FlushBindings();
        Assert.Equal(Visibility.Visible, include.Visibility);
        Assert.Equal(Visibility.Visible, delete.Visibility);
        Assert.Equal(Visibility.Visible, ((TabItem)sourceTabs.Items[2]).Visibility);
    }

    private static void VerifyBoundedLayout(MainWindow window)
    {
        var viewModel = (MainWindowViewModel)window.DataContext;
        for (var index = 0; index < 40; index++)
        {
            viewModel.AddSource();
            viewModel.SelectedSource!.Path = $@"C:\Pictures\Folder-{index}";
        }
        FlushBindings();
        var content = (FrameworkElement)window.Content;
        content.Measure(new Size(960, 590));
        content.Arrange(new Rect(0, 0, 960, 590));
        content.UpdateLayout();
        var saveButton = FindBoundEditor<Button>(content, Button.ContentProperty, "SaveActionButtonText");
        var saveBounds = saveButton.TransformToAncestor(content).TransformBounds(new Rect(saveButton.RenderSize));
        Assert.InRange(saveBounds.Bottom, 1, 590);
        var sourceList = (ListBox)window.FindName("SourceList");
        Assert.InRange(sourceList.ActualHeight, 100, 500);
    }

    private static T FindBoundEditor<T>(object root, DependencyProperty property, string path)
        where T : FrameworkElement
        => FindBoundEditorOrDefault<T>(root, property, path)
           ?? throw new InvalidOperationException($"Missing editor binding: {path}");

    private static T? FindBoundEditorOrDefault<T>(object root, DependencyProperty property, string path)
        where T : FrameworkElement
    {
        if (root is T editor && BindingOperations.GetBinding(editor, property)?.Path.Path == path)
        {
            return editor;
        }

        if (root is DependencyObject dependencyObject)
        {
            foreach (var child in LogicalTreeHelper.GetChildren(dependencyObject))
            {
                var match = FindBoundEditorOrDefault<T>(child, property, path);
                if (match is not null)
                {
                    return match;
                }
            }
        }

        return null;
    }

    private static void RenderPreviewWhenRequested(MainWindow window, TabControl sourceTabs)
    {
        var outputDirectory = Environment.GetEnvironmentVariable("IFW_UI_PREVIEW_DIRECTORY");
        if (string.IsNullOrWhiteSpace(outputDirectory))
        {
            return;
        }

        Directory.CreateDirectory(outputDirectory);
        var viewModel = (MainWindowViewModel)window.DataContext;
        viewModel.ProductVersionText = "Preview · sample data";
        viewModel.SelectedSource!.Path = @"C:\Pictures\Screenshots";
        viewModel.SelectedSource.AlbumName = "Screenshots";
        viewModel.SelectedSource.IncludeSubdirectories = true;
        foreach (var folder in new[] { "Camera", "Scans" })
        {
            viewModel.AddSource();
            viewModel.SelectedSource!.Path = $@"C:\Pictures\{folder}";
            viewModel.SelectedSource.AlbumName = folder;
        }
        viewModel.SelectedSource = viewModel.Sources[0];
        sourceTabs.SelectedIndex = 0;
        var content = (FrameworkElement)window.Content;
        foreach (var theme in new[] { "Light", "Dark" })
        {
            Application.Current.Resources.MergedDictionaries[0] = new ResourceDictionary
            {
                Source = new Uri($"pack://application:,,,/ImmichFolderWatch;component/Styles/Palette{theme}.xaml"),
            };
            for (var section = 0; section < 4; section++)
            {
                viewModel.SelectedSectionIndex = section;
                FlushBindings();
                content.Measure(new Size(1080, 730));
                content.Arrange(new Rect(0, 0, 1080, 730));
                content.UpdateLayout();
                Assert.False(window.IsLoaded);
                var bitmap = new RenderTargetBitmap(1080, 730, 96, 96, PixelFormats.Pbgra32);
                bitmap.Render(content);
                var encoder = new PngBitmapEncoder();
                encoder.Frames.Add(BitmapFrame.Create(bitmap));
                using var stream = File.Create(Path.Combine(outputDirectory, $"windows-{theme.ToLowerInvariant()}-{section}.png"));
                encoder.Save(stream);
            }
        }
    }

    private sealed class TestAutostartManager : IAutoStartManager
    {
        public Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default) => Task.FromResult(false);

        public Task EnableAsync(CancellationToken cancellationToken = default) =>
            throw new InvalidOperationException("The binding check must not modify autostart.");

        public Task DisableAsync(CancellationToken cancellationToken = default) =>
            throw new InvalidOperationException("The binding check must not modify autostart.");
    }
}

// WPF Application and its resources are process-global and owned by one STA.
[CollectionDefinition(nameof(WpfApplicationCollection), DisableParallelization = true)]
public sealed class WpfApplicationCollection
{
}
