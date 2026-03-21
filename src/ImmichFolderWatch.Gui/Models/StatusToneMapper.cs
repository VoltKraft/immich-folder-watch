using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Gui.Models;

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

    public static StatusTone FromServiceStatus(ServiceStatusSnapshot? status)
    {
        if (status is not { Exists: true })
        {
            return StatusTone.Neutral;
        }

        return status.State switch
        {
            ServiceRunState.Running => StatusTone.Success,
            ServiceRunState.Stopped => StatusTone.Warning,
            ServiceRunState.StartPending => StatusTone.Info,
            ServiceRunState.StopPending => StatusTone.Info,
            _ => StatusTone.Neutral,
        };
    }
}
