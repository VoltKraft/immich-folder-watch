using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Services;

public sealed class UpgradeServiceResumePolicyTests
{
    [Fact]
    public void ShouldStartService_ReturnsTrue_WhenServiceWasRunningAndConfigValid()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = true,
            State = ServiceRunState.Stopped,
        };

        var shouldStart = UpgradeServiceResumePolicy.ShouldStartService(
            wasRunningBeforeUpgrade: true,
            snapshot,
            VerificationResult.Passed());

        Assert.True(shouldStart);
    }

    [Theory]
    [InlineData(false, ServiceRunState.Stopped, true)]
    [InlineData(true, ServiceRunState.Running, true)]
    [InlineData(true, ServiceRunState.StartPending, true)]
    [InlineData(true, ServiceRunState.Stopped, false)]
    public void ShouldStartService_ReturnsFalse_WhenResumeConditionsAreNotMet(
        bool wasRunningBeforeUpgrade,
        ServiceRunState serviceState,
        bool verificationSucceeded)
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = true,
            State = serviceState,
        };

        var verificationResult = verificationSucceeded
            ? VerificationResult.Passed()
            : VerificationResult.Failed(["Configuration validation failed."]);

        var shouldStart = UpgradeServiceResumePolicy.ShouldStartService(
            wasRunningBeforeUpgrade,
            snapshot,
            verificationResult);

        Assert.False(shouldStart);
    }

    [Fact]
    public void ShouldStartService_ReturnsFalse_WhenServiceIsNotInstalled()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = false,
            State = ServiceRunState.NotInstalled,
        };

        var shouldStart = UpgradeServiceResumePolicy.ShouldStartService(
            wasRunningBeforeUpgrade: true,
            snapshot,
            VerificationResult.Passed());

        Assert.False(shouldStart);
    }
}
