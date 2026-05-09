using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Logging;

namespace ImmichFolderWatch.Tests.Core.Logging;

public sealed class PlatformLoggingCapabilitiesTests
{
    [Fact]
    public void Linux_SupportsJournaldAndFile()
    {
        var caps = new LinuxLoggingCapabilities();

        Assert.Equal(new[] { LogTargets.Journald, LogTargets.File }, caps.SupportedTargets);
        Assert.Equal(LogTargets.Journald, caps.DefaultTarget);
    }

    [Theory]
    [InlineData(null, LogTargets.Journald)]
    [InlineData("", LogTargets.Journald)]
    [InlineData("eventLog", LogTargets.Journald)]
    [InlineData("EventLog", LogTargets.Journald)]
    [InlineData("file", LogTargets.File)]
    [InlineData("journald", LogTargets.Journald)]
    public void Linux_CoercesUnsupportedToDefault(string? input, string expected)
    {
        var caps = new LinuxLoggingCapabilities();
        Assert.Equal(expected, caps.CoerceToSupported(input));
    }

    [Fact]
    public void Windows_SupportsEventLogAndFile()
    {
        var caps = new WindowsLoggingCapabilities();

        Assert.Equal(new[] { LogTargets.EventLog, LogTargets.File }, caps.SupportedTargets);
        Assert.Equal(LogTargets.EventLog, caps.DefaultTarget);
    }

    [Theory]
    [InlineData(null, LogTargets.EventLog)]
    [InlineData("", LogTargets.EventLog)]
    [InlineData("eventLog", LogTargets.EventLog)]
    [InlineData("file", LogTargets.File)]
    [InlineData("journald", LogTargets.EventLog)]
    [InlineData("Journald", LogTargets.EventLog)]
    public void Windows_CoercesUnsupportedToDefault(string? input, string expected)
    {
        var caps = new WindowsLoggingCapabilities();
        Assert.Equal(expected, caps.CoerceToSupported(input));
    }
}
