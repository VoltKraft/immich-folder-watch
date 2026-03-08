using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

public static class UserInitiatedServiceStartPolicy
{
    public static bool ShouldSwitchToAutomaticDelayedStart(ServiceStatusSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);

        if (!snapshot.Exists)
        {
            return false;
        }

        return snapshot.StartupType is ServiceStartupType.Manual or ServiceStartupType.Disabled or ServiceStartupType.Unknown;
    }
}
