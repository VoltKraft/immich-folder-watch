using ImmichFolderWatch.Core.Installation;

namespace ImmichFolderWatch.Tests.Installation;

public sealed class InstallationPathsTests
{
    [Fact]
    public void GetConfigPath_ReturnsUserLocalAppDataConfigPath()
    {
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (string.IsNullOrWhiteSpace(localAppData))
        {
            localAppData = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                "AppData",
                "Local");
        }

        var configPath = InstallationPaths.GetConfigPath();

        Assert.Equal(
            Path.Combine(localAppData, "Immich Folder Watch", "config.yaml"),
            configPath);
    }

    [Fact]
    public void GetLogDirectory_ReturnsUserLocalAppDataLogsPath()
    {
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (string.IsNullOrWhiteSpace(localAppData))
        {
            localAppData = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                "AppData",
                "Local");
        }

        var logDirectory = InstallationPaths.GetLogDirectory();

        Assert.Equal(
            Path.Combine(localAppData, "Immich Folder Watch", "logs"),
            logDirectory);
    }

    [Fact]
    public void GetLegacyProgramDataConfigPath_ReturnsProgramDataConfigPath()
    {
        var commonAppData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
        if (string.IsNullOrWhiteSpace(commonAppData))
        {
            commonAppData = @"C:\ProgramData";
        }

        var legacyPath = InstallationPaths.GetLegacyProgramDataConfigPath();

        Assert.Equal(
            Path.Combine(commonAppData, "Immich Folder Watch", "config.yaml"),
            legacyPath);
    }
}
