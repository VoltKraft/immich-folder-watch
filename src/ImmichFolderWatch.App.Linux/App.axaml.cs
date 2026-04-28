using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using ImmichFolderWatch.App.Linux.Platform;
using ImmichFolderWatch.App.Linux.ViewModels;
using ImmichFolderWatch.App.Linux.Views;
using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.DependencyInjection;

namespace ImmichFolderWatch.App.Linux;

public sealed partial class App : Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var services = new ServiceCollection();
            services.AddSingleton<IPlatformPaths, XdgPlatformPaths>();
            services.AddSingleton<IAutoStartManager, StubAutoStartManager>();
            services.AddSingleton<IThemeProvider, StubThemeProvider>();
            services.AddSingleton<INotifier, StubNotifier>();
            services.AddSingleton<ISingleInstanceCoordinator, StubSingleInstanceCoordinator>();
            services.AddSingleton<ShellViewModel>();
            var provider = services.BuildServiceProvider();

            desktop.MainWindow = new MainWindow
            {
                DataContext = provider.GetRequiredService<ShellViewModel>(),
            };
        }

        base.OnFrameworkInitializationCompleted();
    }
}
