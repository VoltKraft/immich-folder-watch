using Avalonia;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Themes.Fluent;
using ImmichFolderWatch.App.Shared.Services;
using Xunit;

[assembly: AvaloniaTestApplication(typeof(ImmichFolderWatch.Tests.Linux.TestApplicationBuilder))]
[assembly: CollectionBehavior(DisableTestParallelization = true)]

namespace ImmichFolderWatch.Tests.Linux;

public sealed class TestApplication : Application
{
    public override void Initialize()
    {
        Resources["Loc"] = new LocalizationProxy(LocalizationService.Instance);
        Styles.Add(new FluentTheme());
    }
}

public static class TestApplicationBuilder
{
    public static AppBuilder BuildAvaloniaApp() => AppBuilder.Configure<TestApplication>()
        .UseSkia()
        .WithInterFont()
        .UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false });
}
