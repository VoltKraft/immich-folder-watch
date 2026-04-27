namespace ImmichFolderWatch.Core.Configuration;

public sealed class AppConfig
{
    public ImmichSettings Immich { get; set; } = new();

    public WatchSettings Watch { get; set; } = new();

    public RetrySettings Retry { get; set; } = new();

    public LoggingSettings Logging { get; set; } = new();

    public LocalizationSettings Localization { get; set; } = new();
}

public sealed class ImmichSettings
{
    public string ServerApiUrl { get; set; } = string.Empty;

    public string ApiKey { get; set; } = string.Empty;
}

public sealed class WatchSettings
{
    public List<WatchSourceSettings> Sources { get; set; } = new();

    // Legacy 1.4.x fallback input. New 1.5.0 configs store extensions per source.
    public List<string> Extensions { get; set; } = new();

    public int BatchIntervalSeconds { get; set; } = 5;

    public int MaxBatchSize { get; set; } = 25;

    public int FileReadyTimeoutSeconds { get; set; } = 30;
}

public sealed class WatchSourceSettings
{
    public string Path { get; set; } = string.Empty;

    public string AlbumName { get; set; } = string.Empty;

    public bool IncludeSubdirectories { get; set; }

    public List<string> Extensions { get; set; } = new();

    public List<string> ExcludeDirectories { get; set; } = new();

    public List<string> ExcludeFileNames { get; set; } = new();

    public string SyncMode { get; set; } = WatchSourceSyncModes.UploadNew;
}

public static class WatchSourceSyncModes
{
    public const string UploadNew = "uploadNew";

    public const string UploadAll = "uploadAll";

    public const string Sync = "sync";

    public static string Normalize(string? value)
    {
        var trimmed = (value ?? string.Empty).Trim();
        if (string.IsNullOrEmpty(trimmed))
        {
            return UploadNew;
        }

        if (string.Equals(trimmed, UploadAll, StringComparison.OrdinalIgnoreCase))
        {
            return UploadAll;
        }

        if (string.Equals(trimmed, Sync, StringComparison.OrdinalIgnoreCase))
        {
            return Sync;
        }

        return UploadNew;
    }
}

public sealed class RetrySettings
{
    public int MaxAttempts { get; set; } = 5;

    public int BaseDelayMilliseconds { get; set; } = 500;
}

public sealed class LoggingSettings
{
    public string Level { get; set; } = "Information";

    public string Target { get; set; } = LogTargets.EventLog;

    public string LogDirectory { get; set; } = "logs";
}

public static class LogTargets
{
    public const string EventLog = "eventLog";

    public const string File = "file";

    public static IReadOnlyList<string> All { get; } = new[] { EventLog, File };

    public static string Normalize(string? value)
    {
        var trimmed = (value ?? string.Empty).Trim();
        if (string.IsNullOrEmpty(trimmed))
        {
            return EventLog;
        }

        if (string.Equals(trimmed, EventLog, StringComparison.OrdinalIgnoreCase))
        {
            return EventLog;
        }

        if (string.Equals(trimmed, File, StringComparison.OrdinalIgnoreCase))
        {
            return File;
        }

        return EventLog;
    }

    public static bool IsEventLog(string? value) =>
        string.Equals(Normalize(value), EventLog, StringComparison.Ordinal);

    public static bool IsFile(string? value) =>
        string.Equals(Normalize(value), File, StringComparison.Ordinal);
}

public sealed class LocalizationSettings
{
    public string Language { get; set; } = "auto";
}
