using ImmichFolderWatch.Core.Installation;

namespace ImmichFolderWatch.Tests.Installation;

public sealed class InstallationPathsTests
{
    [Fact]
    public void GetConfigPath_ReturnsProgramDataConfigPath()
    {
        var baseDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            "Immich Folder Watch",
            "bin");
        var commonApplicationData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
        if (string.IsNullOrWhiteSpace(commonApplicationData))
        {
            commonApplicationData = @"C:\ProgramData";
        }

        var configPath = InstallationPaths.GetConfigPath(baseDirectory);

        Assert.Equal(
            Path.Combine(commonApplicationData, "Immich Folder Watch", "config.yaml"),
            configPath);
    }

    [Fact]
    public void GetLogDirectory_ReturnsProgramDataLogsPath()
    {
        var baseDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            "Immich Folder Watch",
            "bin");
        var commonApplicationData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
        if (string.IsNullOrWhiteSpace(commonApplicationData))
        {
            commonApplicationData = @"C:\ProgramData";
        }

        var logDirectory = InstallationPaths.GetLogDirectory(baseDirectory);

        Assert.Equal(
            Path.Combine(commonApplicationData, "Immich Folder Watch", "logs"),
            logDirectory);
    }
}
