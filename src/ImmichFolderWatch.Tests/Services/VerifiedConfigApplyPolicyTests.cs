using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Services;

public sealed class VerifiedConfigApplyPolicyTests
{
    [Fact]
    public void Determine_RunningService_RestartsOnly()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = true,
            State = ServiceRunState.Running,
            StartupType = ServiceStartupType.Automatic,
            DelayedAutoStart = true,
        };

        var actions = VerifiedConfigApplyPolicy.Determine(snapshot);

        Assert.False(actions.StartService);
        Assert.True(actions.RestartService);
    }

    [Fact]
    public void Determine_StoppedService_StartsService()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = true,
            State = ServiceRunState.Stopped,
            StartupType = ServiceStartupType.Disabled,
        };

        var actions = VerifiedConfigApplyPolicy.Determine(snapshot);

        Assert.True(actions.StartService);
        Assert.False(actions.RestartService);
    }

    [Fact]
    public void Determine_StartPendingService_DoesNothing()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = true,
            State = ServiceRunState.StartPending,
            StartupType = ServiceStartupType.Automatic,
        };

        var actions = VerifiedConfigApplyPolicy.Determine(snapshot);

        Assert.False(actions.StartService);
        Assert.False(actions.RestartService);
    }

    [Fact]
    public void Determine_MissingService_DoesNothing()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = false,
            State = ServiceRunState.NotInstalled,
            StartupType = ServiceStartupType.Unknown,
        };

        var actions = VerifiedConfigApplyPolicy.Determine(snapshot);

        Assert.False(actions.StartService);
        Assert.False(actions.RestartService);
    }
}
