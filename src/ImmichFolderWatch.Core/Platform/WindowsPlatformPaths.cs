using ImmichFolderWatch.Core.Installation;

namespace ImmichFolderWatch.Core.Platform;

public sealed class WindowsPlatformPaths : IPlatformPaths
{
    public string ProductFolderName => InstallationPaths.ProductFolderName;

    public string GetUserDataRoot() => InstallationPaths.GetUserDataRoot();

    public string GetConfigPath() => InstallationPaths.GetConfigPath();

    public string GetSyncDatabasePath() => InstallationPaths.GetSyncDatabasePath();

    public string GetLogDirectory() => InstallationPaths.GetLogDirectory();
}
