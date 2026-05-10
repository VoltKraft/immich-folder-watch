using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.Tests.Core.Platform;

public sealed class WindowsPlatformPathsTests
{
    [Fact]
    public void ProductFolderName_MatchesInstallationPathsConstant()
    {
        var paths = new WindowsPlatformPaths();

        Assert.Equal(InstallationPaths.ProductFolderName, paths.ProductFolderName);
    }

    [Fact]
    public void GetUserDataRoot_DelegatesToInstallationPaths()
    {
        var paths = new WindowsPlatformPaths();

        Assert.Equal(InstallationPaths.GetUserDataRoot(), paths.GetUserDataRoot());
    }

    [Fact]
    public void GetConfigPath_DelegatesToInstallationPaths()
    {
        var paths = new WindowsPlatformPaths();

        Assert.Equal(InstallationPaths.GetConfigPath(), paths.GetConfigPath());
    }

    [Fact]
    public void GetLogDirectory_DelegatesToInstallationPaths()
    {
        var paths = new WindowsPlatformPaths();

        Assert.Equal(InstallationPaths.GetLogDirectory(), paths.GetLogDirectory());
    }

    [Fact]
    public void Implements_IPlatformPaths()
    {
        IPlatformPaths paths = new WindowsPlatformPaths();

        Assert.NotNull(paths);
        Assert.False(string.IsNullOrWhiteSpace(paths.GetConfigPath()));
        Assert.False(string.IsNullOrWhiteSpace(paths.GetLogDirectory()));
    }
}
