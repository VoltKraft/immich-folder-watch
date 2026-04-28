using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Tests.Core.Configuration;

public sealed class AppConfigValidatorWindowsPathTests
{
    [Theory]
    [InlineData(@"C:\Users\jan\Pictures", true)]
    [InlineData(@"D:\Photos\2026", true)]
    [InlineData(@"c:/Users/jan/Pictures", true)]
    [InlineData("/home/jan/Pictures", false)]
    [InlineData("relative/path", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    [InlineData(@"\\server\share", false)]
    public void LooksLikeWindowsPath_DetectsDriveLetterPrefix(string? path, bool expected)
    {
        Assert.Equal(expected, AppConfigValidator.LooksLikeWindowsPath(path));
    }

    [Fact]
    public void Validate_OnNonWindows_RejectsWindowsStylePathsWithSpecificError()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        var logPath = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), $"ifw-logs-{Guid.NewGuid():N}")).FullName;
        try
        {
            var config = BuildConfigWithSourcePath(@"C:\Users\jan\Pictures", logPath);

            var errors = AppConfigValidator.Validate(config);

            Assert.Contains(errors, e => e.Contains("looks like a Windows path", StringComparison.Ordinal)
                                       && e.Contains(@"C:\Users\jan\Pictures", StringComparison.Ordinal));
        }
        finally
        {
            Directory.Delete(logPath, recursive: true);
        }
    }

    [Fact]
    public void Validate_OnNonWindows_DoesNotRejectPosixPaths()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        var watchPath = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), $"ifw-watch-{Guid.NewGuid():N}")).FullName;
        var logPath = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), $"ifw-logs-{Guid.NewGuid():N}")).FullName;
        try
        {
            var config = BuildConfigWithSourcePath(watchPath, logPath);

            var errors = AppConfigValidator.Validate(config);

            Assert.DoesNotContain(errors, e => e.Contains("looks like a Windows path", StringComparison.Ordinal));
        }
        finally
        {
            Directory.Delete(watchPath, recursive: true);
            Directory.Delete(logPath, recursive: true);
        }
    }

    private static AppConfig BuildConfigWithSourcePath(string path, string logPath)
        => new()
        {
            Immich = new ImmichSettings
            {
                ServerApiUrl = "https://immich.example.com/api",
                ApiKey = "demo-key",
            },
            Watch = new WatchSettings
            {
                Sources =
                [
                    new WatchSourceSettings
                    {
                        Path = path,
                        Extensions = [".png"],
                    },
                ],
            },
            Logging = new LoggingSettings
            {
                Level = "Information",
                LogDirectory = logPath,
            },
        };
}
