using ImmichFolderWatch.App.Linux.Platform;
using ImmichFolderWatch.App.Shared.Resources;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Linux;

[Collection("Localization")]
public sealed class TrayStatusTextTests
{
    [Fact]
    public void Compose_ReflectsStatusQueueLastSyncAndLanguageChanges()
    {
        var localization = LocalizationService.Instance;
        var original = localization.CurrentLanguage;
        try
        {
            localization.SetLanguage("en");
            var status = new SyncStatusProvider();
            var initial = TrayStatusText.Compose(status, localization);
            Assert.Contains(Strings.Server_Unknown, initial);
            Assert.Contains("—", initial);
            status.ReportServerReachable(true);
            status.ReportPendingCount(42);
            var completed = new DateTimeOffset(2026, 9, 9, 9, 15, 0, TimeSpan.Zero);
            status.RestoreLastSyncCompleted(completed);
            var updated = TrayStatusText.Compose(status, localization);
            Assert.Contains(Strings.Server_Ok, updated);
            Assert.Contains("42", updated);
            Assert.Contains(completed.ToLocalTime().ToString("HH:mm", localization.CurrentCulture), updated);
            localization.SetLanguage("de");
            var translated = TrayStatusText.Compose(status, localization);
            Assert.Contains(Strings.UI_ServerConnection, translated);
            Assert.NotEqual(updated, translated);
        }
        finally
        {
            localization.SetLanguage(original);
        }
    }
}
