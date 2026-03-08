using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Services;

public sealed class UserInitiatedServiceStartPolicyTests
{
    [Theory]
    [InlineData(ServiceStartupType.Manual, false, true)]
    [InlineData(ServiceStartupType.Disabled, false, true)]
    [InlineData(ServiceStartupType.Unknown, false, true)]
    [InlineData(ServiceStartupType.Automatic, false, false)]
    [InlineData(ServiceStartupType.Automatic, true, false)]
    public void ShouldSwitchToAutomaticDelayedStart_ReturnsExpectedValue(
        ServiceStartupType startupType,
        bool delayedAutoStart,
        bool expected)
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = true,
            StartupType = startupType,
            DelayedAutoStart = delayedAutoStart,
        };

        var result = UserInitiatedServiceStartPolicy.ShouldSwitchToAutomaticDelayedStart(snapshot);

        Assert.Equal(expected, result);
    }

    [Fact]
    public void ShouldSwitchToAutomaticDelayedStart_ReturnsFalse_WhenServiceIsMissing()
    {
        var snapshot = new ServiceStatusSnapshot
        {
            Exists = false,
            StartupType = ServiceStartupType.Manual,
        };

        var result = UserInitiatedServiceStartPolicy.ShouldSwitchToAutomaticDelayedStart(snapshot);

        Assert.False(result);
    }
}
