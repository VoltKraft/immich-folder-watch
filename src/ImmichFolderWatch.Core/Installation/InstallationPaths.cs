namespace ImmichFolderWatch.Core.Installation;

public static class InstallationPaths
{
    public const string ProductFolderName = "Immich Folder Watch";
    public const string ConfigFileName = "config.yaml";
    public const string SyncDatabaseFileName = "sync-state.db";
    public const string LogsDirectoryName = "logs";
    public const string AutostartShortcutName = "Immich Folder Watch.lnk";
    public const string LegacyServiceName = "ImmichFolderWatch";
    public const string AppExecutableName = "ImmichFolderWatch.exe";

    public static string GetUserDataRoot()
    {
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (string.IsNullOrWhiteSpace(localAppData))
        {
            localAppData = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                "AppData",
                "Local");
        }

        return Path.Combine(localAppData, ProductFolderName);
    }

    public static string GetConfigPath() => Path.Combine(GetUserDataRoot(), ConfigFileName);

    public static string GetSyncDatabasePath() => Path.Combine(GetUserDataRoot(), SyncDatabaseFileName);

    public static string GetLogDirectory() => Path.Combine(GetUserDataRoot(), LogsDirectoryName);

    public static string GetLegacyProgramDataRoot()
    {
        var commonAppData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
        if (string.IsNullOrWhiteSpace(commonAppData))
        {
            commonAppData = @"C:\ProgramData";
        }

        return Path.Combine(commonAppData, ProductFolderName);
    }

    public static string GetLegacyProgramDataConfigPath() =>
        Path.Combine(GetLegacyProgramDataRoot(), ConfigFileName);

    public static string GetStartupShortcutPath()
    {
        var startupFolder = Environment.GetFolderPath(Environment.SpecialFolder.Startup);
        return Path.Combine(startupFolder, AutostartShortcutName);
    }

    public static string GetAppExecutablePath(string baseDirectory)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(baseDirectory);
        return Path.Combine(baseDirectory, AppExecutableName);
    }
}
