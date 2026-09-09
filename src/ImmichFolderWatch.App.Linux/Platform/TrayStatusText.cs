using ImmichFolderWatch.App.Shared.Resources;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.App.Linux.Platform;

internal static class TrayStatusText
{
    public static string Compose(SyncStatusProvider status, LocalizationService localization)
    {
        var server = status.ServerConnection switch
        {
            ServerConnectionState.Ok => Strings.Server_Ok,
            ServerConnectionState.Error => Strings.Server_Error,
            ServerConnectionState.Checking => Strings.Server_Checking,
            _ => Strings.Server_Unknown,
        };
        var culture = localization.CurrentCulture;
        var lastSync = status.LastSyncCompletedUtc?.ToLocalTime().ToString("HH:mm", culture) ?? "—";
        return string.Create(culture,
            $"Immich Folder Watch\n{Strings.UI_ServerConnection}: {server}\n{Strings.Tooltip_LastSync}: {lastSync}\n{Strings.Tooltip_Queue}: {status.PendingCount}");
    }
}
