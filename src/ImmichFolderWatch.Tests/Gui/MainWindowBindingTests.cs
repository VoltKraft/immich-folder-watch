using System.Runtime.ExceptionServices;
using System.Threading;
using System.Windows;
using System.Windows.Data;
using System.Windows.Documents;
using ImmichFolderWatch.App;
using ImmichFolderWatch.App.Hosting;
using ImmichFolderWatch.App.Services;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Services;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Gui;

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
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        thread.Join();

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
        application.Resources["Loc"] = new LocalizationProxy();

        var syncStatusProvider = new SyncStatusProvider();
        var appHost = new AppHost(syncStatusProvider);
        var window = new MainWindow(
            appHost,
            syncStatusProvider,
            new AutostartManager(),
            new AppConfigLoader(),
            new ThemeWatcher(application),
            LocalizationService.Instance,
            NullLogger<MainWindow>.Instance,
            "Version 2.8.1");

        try
        {
            var run = Assert.IsType<Run>(window.FindName("UpdateAvailableTextRun"));
            var binding = BindingOperations.GetBinding(run, Run.TextProperty);

            Assert.NotNull(binding);
            Assert.Equal(BindingMode.OneWay, binding.Mode);
        }
        finally
        {
            window.Close();
            appHost.DisposeAsync().AsTask().GetAwaiter().GetResult();
            application.Shutdown();
        }
    }
}
