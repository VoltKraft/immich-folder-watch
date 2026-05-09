using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Tests.Core.Configuration;

public sealed class LogTargetsTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("bogus")]
    [InlineData("disk")]
    public void Normalize_NullEmptyOrUnknown_DefaultsToEventLog(string? value)
    {
        Assert.Equal(LogTargets.EventLog, LogTargets.Normalize(value));
    }

    [Theory]
    [InlineData("eventLog")]
    [InlineData("EVENTLOG")]
    [InlineData(" EventLog ")]
    public void Normalize_EventLogVariants_Normalize(string value)
    {
        Assert.Equal(LogTargets.EventLog, LogTargets.Normalize(value));
    }

    [Theory]
    [InlineData("file")]
    [InlineData("FILE")]
    [InlineData(" File ")]
    public void Normalize_FileVariants_Normalize(string value)
    {
        Assert.Equal(LogTargets.File, LogTargets.Normalize(value));
    }

    [Theory]
    [InlineData("journald")]
    [InlineData("JOURNALD")]
    [InlineData(" Journald ")]
    public void Normalize_JournaldVariants_Normalize(string value)
    {
        Assert.Equal(LogTargets.Journald, LogTargets.Normalize(value));
    }

    [Fact]
    public void Helpers_ReportCorrectTarget()
    {
        Assert.True(LogTargets.IsEventLog("eventLog"));
        Assert.True(LogTargets.IsEventLog(null));
        Assert.False(LogTargets.IsEventLog("file"));

        Assert.True(LogTargets.IsFile("file"));
        Assert.False(LogTargets.IsFile("eventLog"));
        Assert.False(LogTargets.IsFile(null));

        Assert.True(LogTargets.IsJournald("journald"));
        Assert.False(LogTargets.IsJournald("file"));
        Assert.False(LogTargets.IsJournald(null));
    }

    [Fact]
    public void All_ContainsAllCanonicalValues()
    {
        Assert.Contains(LogTargets.EventLog, LogTargets.All);
        Assert.Contains(LogTargets.File, LogTargets.All);
        Assert.Contains(LogTargets.Journald, LogTargets.All);
    }
}
