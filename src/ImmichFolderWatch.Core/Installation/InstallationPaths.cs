namespace ImmichFolderWatch.Core.Installation;

public static class InstallationPaths
{
    public const string ServiceName = "ImmichFolderWatch";
    public const string DataDirectoryName = "Immich Folder Watch";

    public static string GetInstallRoot(string baseDirectory)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(baseDirectory);
        return Path.GetFullPath(Path.Combine(baseDirectory, ".."));
    }

    public static string GetDataRoot()
    {
        var commonApplicationData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
        if (string.IsNullOrWhiteSpace(commonApplicationData))
        {
            commonApplicationData = @"C:\ProgramData";
        }

        return Path.Combine(commonApplicationData, DataDirectoryName);
    }

    public static string GetLegacyStructuredConfigPath(string legacyInstallRoot)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(legacyInstallRoot);
        return Path.Combine(Path.GetFullPath(legacyInstallRoot), "config", "config.yaml");
    }

    public static string GetLegacyRootConfigPath(string legacyInstallRoot)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(legacyInstallRoot);
        return Path.Combine(Path.GetFullPath(legacyInstallRoot), "config.yaml");
    }

    public static string GetLegacyDefaultLogDirectory(string legacyInstallRoot)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(legacyInstallRoot);
        return Path.Combine(Path.GetFullPath(legacyInstallRoot), "logs");
    }

    public static string GetConfigDirectory(string baseDirectory)
    {
        return GetDataRoot();
    }

    public static string GetConfigPath(string baseDirectory)
    {
        return Path.Combine(GetDataRoot(), "config.yaml");
    }

    public static string GetLogDirectory(string baseDirectory)
    {
        return Path.Combine(GetDataRoot(), "logs");
    }

    public static string GetAdminExecutablePath(string baseDirectory)
    {
        return Path.Combine(baseDirectory, "ImmichFolderWatch.Admin.exe");
    }

    public static string GetGuiExecutablePath(string baseDirectory)
    {
        return Path.Combine(baseDirectory, "ImmichFolderWatch.Gui.exe");
    }
}
