namespace ImmichFolderWatch.Core.Platform;

public sealed class XdgPlatformPaths : IPlatformPaths
{
    private const string DefaultProductFolderName = "immich-folder-watch";

    public XdgPlatformPaths()
        : this(DefaultProductFolderName)
    {
    }

    public XdgPlatformPaths(string productFolderName)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(productFolderName);
        ProductFolderName = productFolderName;
    }

    public string ProductFolderName { get; }

    public string GetUserDataRoot() => Path.Combine(ResolveXdgDir("XDG_CONFIG_HOME", ".config"), ProductFolderName);

    public string GetConfigPath() => Path.Combine(GetUserDataRoot(), "config.yaml");

    public string GetSyncDatabasePath() => Path.Combine(GetUserDataRoot(), "sync-state.db");

    public string GetLogDirectory() => Path.Combine(ResolveXdgDir("XDG_STATE_HOME", Path.Combine(".local", "state")), ProductFolderName, "logs");

    private static string ResolveXdgDir(string envVar, string fallbackBelowHome)
    {
        var value = Environment.GetEnvironmentVariable(envVar);
        if (!string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        var home = Environment.GetEnvironmentVariable("HOME");
        if (string.IsNullOrWhiteSpace(home))
        {
            home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        }

        return Path.Combine(home, fallbackBelowHome);
    }
}
