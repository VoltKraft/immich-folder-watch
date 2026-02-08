namespace ImmichFolderWatch.Core.Configuration;

public sealed class AppConfig
{
    public ImmichSettings Immich { get; set; } = new();

    public WatchSettings Watch { get; set; } = new();

    public RetrySettings Retry { get; set; } = new();

    public LoggingSettings Logging { get; set; } = new();
}

public sealed class ImmichSettings
{
    public string ServerApiUrl { get; set; } = string.Empty;

    public string ApiKey { get; set; } = string.Empty;
}

public sealed class WatchSettings
{
    public List<WatchSourceSettings> Sources { get; set; } = new();

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
}

public sealed class RetrySettings
{
    public int MaxAttempts { get; set; } = 5;

    public int BaseDelayMilliseconds { get; set; } = 500;
}

public sealed class LoggingSettings
{
    public string Level { get; set; } = "Information";

    public string LogDirectory { get; set; } = "logs";
}
