using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

public static class UpgradeServiceResumePolicy
{
    public static bool ShouldStartService(
        bool wasRunningBeforeUpgrade,
        ServiceStatusSnapshot snapshot,
        VerificationResult verificationResult)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ArgumentNullException.ThrowIfNull(verificationResult);

        return wasRunningBeforeUpgrade
            && snapshot.Exists
            && snapshot.State == ServiceRunState.Stopped
            && verificationResult.Success;
    }
}
