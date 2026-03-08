using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

public static class VerifiedConfigApplyPolicy
{
    public static ConfigApplyActions Determine(ServiceStatusSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);

        if (!snapshot.IsInitialVerificationCompleted)
        {
            return new ConfigApplyActions
            {
                SetAutomaticDelayedStart = true,
                StartService = true,
                MarkInitialVerificationCompleted = true,
            };
        }

        if (snapshot.State == ServiceRunState.Running)
        {
            return new ConfigApplyActions
            {
                RestartService = true,
            };
        }

        return new ConfigApplyActions();
    }
}
