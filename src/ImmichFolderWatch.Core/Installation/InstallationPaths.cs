namespace ImmichFolderWatch.Core.Installation;

public static class InstallationPaths
{
    public const string ServiceName = "ImmichFolderWatch";

    public static string GetInstallRoot(string baseDirectory)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(baseDirectory);
        return Path.GetFullPath(Path.Combine(baseDirectory, ".."));
    }

    public static string GetConfigDirectory(string baseDirectory)
    {
        return Path.Combine(GetInstallRoot(baseDirectory), "config");
    }

    public static string GetConfigPath(string baseDirectory)
    {
        return Path.Combine(GetConfigDirectory(baseDirectory), "config.yaml");
    }

    public static string GetLogDirectory(string baseDirectory)
    {
        return Path.Combine(GetInstallRoot(baseDirectory), "logs");
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
