using System.Text.Json;
using Avalonia.Headless.XUnit;
using Avalonia.Threading;
using ImmichFolderWatch.App.Linux.Views;
using ImmichFolderWatch.App.Shared.Resources;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

/// <summary>
/// Executes language-neutral lifecycle traces against the real legacy view.
/// The headless application cannot start production services or read a user profile.
/// Native desktop reachability and engine shutdown remain separate acceptance gates.
/// </summary>
public sealed class RustRewriteLifecycleContractTests
{
    [AvaloniaTheory]
    [InlineData("LIFE-01-close-reopen-quit")]
    [InlineData("LIFE-02-background-fallback-once")]
    [InlineData("LIFE-03-background-tray-loss")]
    [InlineData("LIFE-04-closed-before-tray-reply")]
    [InlineData("LIFE-05-shutdown-prevents-fallback")]
    public void SyntheticTrace_MatchesLegacyWindow(string id)
    {
        Assert.Null(ImmichFolderWatch.App.Linux.App.Services);
        using var document = JsonDocument.Parse(File.ReadAllText(FindFixture()));
        var scenario = document.RootElement.GetProperty("cases").EnumerateArray()
            .Single(value => value.GetProperty("id").GetString() == id);
        var previousLanguage = LocalizationService.Instance.CurrentLanguage;
        LocalizationService.Instance.SetLanguage(LocalizationService.LanguageEnglish);
        var viewModel = new MainWindowViewModel(new SyncStatusProvider(), new IsolatedAutostart(),
            LocalizationService.Instance, new UiDispatcher(), new LinuxLoggingCapabilities());
        var window = new MainWindow { DataContext = viewModel };
        var closed = false;
        window.Closed += (_, _) => closed = true;
        try
        {
            Assert.False(window.IsVisible);
            foreach (var step in scenario.GetProperty("steps").EnumerateArray())
            {
                switch (step.GetProperty("command").GetString())
                {
                    case "show": window.Show(); break;
                    case "close": window.Close(); break;
                    case "trayAvailable": window.UpdateTrayAvailability(true); break;
                    case "trayUnavailable": window.UpdateTrayAvailability(false); break;
                    case "beginShutdown": window.IsExiting = true; break;
                    case "quit": window.IsExiting = true; window.Close(); break;
                    default: throw new InvalidDataException($"Unknown lifecycle command in {id}.");
                }
                Dispatcher.UIThread.RunJobs();
                if (!closed) window.UpdateLayout();
                Dispatcher.UIThread.RunJobs();
                Assert.Equal(step.GetProperty("visible").GetBoolean(), window.IsVisible);
                Assert.Equal(step.GetProperty("closed").GetBoolean(), closed);
                Assert.Equal(step.GetProperty("trayUnavailable").GetBoolean()
                    ? Strings.Tray_Unavailable : string.Empty, viewModel.TrayStatusMessage);
            }
        }
        finally
        {
            window.IsExiting = true;
            if (!closed) window.Close();
            window.DataContext = null;
            LocalizationService.Instance.SetLanguage(previousLanguage);
        }
    }

    private static string FindFixture()
    {
        const string relative = "rust/tests/fixtures/lifecycle/window.json";
        var explicitRoot = Environment.GetEnvironmentVariable("IFW_COMPATIBILITY_REPOSITORY");
        if (!string.IsNullOrWhiteSpace(explicitRoot)) return Path.Combine(explicitRoot, relative);
        for (var current = new DirectoryInfo(AppContext.BaseDirectory); current is not null; current = current.Parent)
        {
            var path = Path.Combine(current.FullName, relative);
            if (File.Exists(path)) return path;
        }
        throw new FileNotFoundException("Run the lifecycle corpus inside its repository or set IFW_COMPATIBILITY_REPOSITORY.");
    }

    private sealed class IsolatedAutostart : IAutoStartManager
    {
        public Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default) => Task.FromResult(false);
        public Task EnableAsync(CancellationToken cancellationToken = default) =>
            throw new InvalidOperationException("Autostart writes are forbidden in the lifecycle oracle.");
        public Task DisableAsync(CancellationToken cancellationToken = default) =>
            throw new InvalidOperationException("Autostart writes are forbidden in the lifecycle oracle.");
    }

    private sealed class UiDispatcher : IUiDispatcher
    {
        public bool IsOnUiThread => Dispatcher.UIThread.CheckAccess();
        public void Post(Action action) => Dispatcher.UIThread.Post(action);
    }
}
