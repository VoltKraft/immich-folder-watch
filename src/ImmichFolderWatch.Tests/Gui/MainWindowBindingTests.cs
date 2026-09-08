using System.Runtime.ExceptionServices;
using System.Threading;
using System.Windows;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Threading;
using ImmichFolderWatch.App;
using ImmichFolderWatch.App.Hosting;
using ImmichFolderWatch.App.Services;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Gui;

[Collection(nameof(WpfApplicationCollection))]
public sealed class MainWindowBindingTests
{
    [Fact]
    public void UpdateAvailableTextBinding_IsOneWay()
    {
        Exception? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                VerifyUpdateAvailableTextBinding();
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

    private static void VerifyUpdateAvailableTextBinding()
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
            var run = Assert.IsType<Run>(window.FindName("UpdateAvailableTextRun"));
            var binding = BindingOperations.GetBinding(run, Run.TextProperty);

            Assert.NotNull(binding);
            Assert.Equal(BindingMode.OneWay, binding.Mode);
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
