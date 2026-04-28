using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.App.Shared.Models;

public static class StatusToneMapper
{
    public static StatusTone FromCheckState(CheckState state)
    {
        return state switch
        {
            CheckState.Passed => StatusTone.Success,
            CheckState.Warning => StatusTone.Warning,
            CheckState.Failed => StatusTone.Error,
            CheckState.Checking => StatusTone.Info,
            _ => StatusTone.Neutral,
        };
    }

    public static StatusTone FromServerConnection(ServerConnectionState state)
    {
        return state switch
        {
            ServerConnectionState.Ok => StatusTone.Success,
            ServerConnectionState.Error => StatusTone.Error,
            ServerConnectionState.Checking => StatusTone.Info,
            _ => StatusTone.Neutral,
        };
    }
}
