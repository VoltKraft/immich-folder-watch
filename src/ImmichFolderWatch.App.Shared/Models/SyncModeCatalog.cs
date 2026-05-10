namespace ImmichFolderWatch.App.Shared.Models;

/// <summary>
/// Process-wide catalog of <see cref="SyncModeOption"/> instances —
/// populated by <c>MainWindowViewModel.RefreshSyncModeOptions</c> with
/// the SAME array that backs <c>AvailableSyncModes</c>, so look-ups
/// from <see cref="WatchSourceItem.SelectedSyncModeOption"/> return
/// reference-equal instances and the Avalonia ComboBox can match them
/// against its ItemsSource. Re-populated on language change so the
/// localized DisplayName follows the current culture.
/// </summary>
internal static class SyncModeCatalog
{
    private static IReadOnlyList<SyncModeOption> _options = Array.Empty<SyncModeOption>();

    public static void SetOptions(IReadOnlyList<SyncModeOption> options)
    {
        _options = options ?? Array.Empty<SyncModeOption>();
    }

    public static SyncModeOption? FindByCode(string? code)
    {
        if (string.IsNullOrEmpty(code))
        {
            return null;
        }

        for (var i = 0; i < _options.Count; i++)
        {
            if (string.Equals(_options[i].Code, code, StringComparison.Ordinal))
            {
                return _options[i];
            }
        }

        return null;
    }
}
