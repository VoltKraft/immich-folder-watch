using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

public static class VerifiedConfigApplyPolicy
{
    public static ConfigApplyActions Determine(ServiceStatusSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);

        if (snapshot.State == ServiceRunState.Running)
        {
            return new ConfigApplyActions
            {
                RestartService = true,
            };
        }

        if (snapshot.State == ServiceRunState.Stopped)
        {
            return new ConfigApplyActions
            {
                StartService = true,
            };
        }

        return new ConfigApplyActions();
    }
}
