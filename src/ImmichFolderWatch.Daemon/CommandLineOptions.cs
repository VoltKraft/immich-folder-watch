namespace ImmichFolderWatch.Daemon;

internal sealed class CommandLineOptions
{
    public const string Usage = "Usage: ImmichFolderWatch.Daemon --config <path> | --version";

    private CommandLineOptions(string? configPath, bool versionRequested)
    {
        ConfigPath = configPath;
        VersionRequested = versionRequested;
    }

    public string? ConfigPath { get; }

    public bool VersionRequested { get; }

    public static bool TryParse(string[] args, out CommandLineOptions? options, out string message, out bool helpRequested)
    {
        options = null;
        helpRequested = false;

        if (args.Length == 1 && (string.Equals(args[0], "--help", StringComparison.OrdinalIgnoreCase)
            || string.Equals(args[0], "-h", StringComparison.OrdinalIgnoreCase)))
        {
            message = Usage;
            helpRequested = true;
            return false;
        }

        if (args.Length == 1 && (string.Equals(args[0], "--version", StringComparison.OrdinalIgnoreCase)
            || string.Equals(args[0], "-v", StringComparison.OrdinalIgnoreCase)))
        {
            options = new CommandLineOptions(configPath: null, versionRequested: true);
            message = string.Empty;
            return true;
        }

        if (args.Length == 2 && string.Equals(args[0], "--config", StringComparison.OrdinalIgnoreCase))
        {
            var configPath = args[1]?.Trim();
            if (!string.IsNullOrWhiteSpace(configPath))
            {
                options = new CommandLineOptions(configPath, versionRequested: false);
                message = string.Empty;
                return true;
            }
        }

        message = $"Invalid arguments. {Usage}";
        return false;
    }
}
