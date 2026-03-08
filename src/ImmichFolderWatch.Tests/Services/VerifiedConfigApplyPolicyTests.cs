using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Services;

public sealed class VerifiedConfigApplyPolicyTests
{
    [Fact]
    public void Determine_FirstVerification_EnablesAndStartsService()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = true,
            State = ServiceRunState.Stopped,
            StartupType = ServiceStartupType.Disabled,
            IsInitialVerificationCompleted = false,
        };

        var actions = VerifiedConfigApplyPolicy.Determine(snapshot);

        Assert.True(actions.SetAutomaticDelayedStart);
        Assert.True(actions.StartService);
        Assert.False(actions.RestartService);
        Assert.True(actions.MarkInitialVerificationCompleted);
    }

    [Fact]
    public void Determine_RunningVerifiedService_RestartsOnly()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = true,
            State = ServiceRunState.Running,
            StartupType = ServiceStartupType.Automatic,
            DelayedAutoStart = true,
            IsInitialVerificationCompleted = true,
        };

        var actions = VerifiedConfigApplyPolicy.Determine(snapshot);

        Assert.False(actions.SetAutomaticDelayedStart);
        Assert.False(actions.StartService);
        Assert.True(actions.RestartService);
        Assert.False(actions.MarkInitialVerificationCompleted);
    }

    [Fact]
    public void Determine_StoppedVerifiedService_StartsService()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = true,
            State = ServiceRunState.Stopped,
            StartupType = ServiceStartupType.Disabled,
            IsInitialVerificationCompleted = true,
        };

        var actions = VerifiedConfigApplyPolicy.Determine(snapshot);

        Assert.False(actions.SetAutomaticDelayedStart);
        Assert.True(actions.StartService);
        Assert.False(actions.RestartService);
        Assert.False(actions.MarkInitialVerificationCompleted);
    }
}
