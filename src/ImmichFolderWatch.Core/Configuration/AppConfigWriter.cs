using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace ImmichFolderWatch.Core.Configuration;

public sealed class AppConfigWriter
{
    public string Serialize(AppConfig config)
    {
        ArgumentNullException.ThrowIfNull(config);

        config.Watch ??= new WatchSettings();
        config.Watch.Sources ??= new List<WatchSourceSettings>();
        config.Watch.Extensions ??= new List<string>();
        var legacyExtensions = config.Watch.Extensions.ToList();

        var serializer = new SerializerBuilder()
            .WithNamingConvention(CamelCaseNamingConvention.Instance)
            .Build();

        var writableConfig = new WritableAppConfig
        {
            Immich = new ImmichSettings
            {
                ServerApiUrl = config.Immich.ServerApiUrl,
                ApiKey = config.Immich.ApiKey,
            },
            Watch = new WritableWatchSettings
            {
                Sources = (config.Watch.Sources ?? new List<WatchSourceSettings>())
                    .Select(source => new WritableWatchSourceSettings
                    {
                        Path = source.Path,
                        AlbumName = source.AlbumName,
                        IncludeSubdirectories = source.IncludeSubdirectories,
                        Extensions = (source.Extensions?.Count ?? 0) > 0
                            ? (source.Extensions ?? new List<string>()).ToList()
                            : legacyExtensions.ToList(),
                        ExcludeDirectories = (source.ExcludeDirectories ?? new List<string>()).ToList(),
                        ExcludeFileNames = (source.ExcludeFileNames ?? new List<string>()).ToList(),
                    })
                    .ToList(),
                BatchIntervalSeconds = config.Watch.BatchIntervalSeconds,
                MaxBatchSize = config.Watch.MaxBatchSize,
                FileReadyTimeoutSeconds = config.Watch.FileReadyTimeoutSeconds,
            },
            Retry = new RetrySettings
            {
                MaxAttempts = config.Retry.MaxAttempts,
                BaseDelayMilliseconds = config.Retry.BaseDelayMilliseconds,
            },
            Logging = new LoggingSettings
            {
                Level = config.Logging.Level,
                LogDirectory = config.Logging.LogDirectory,
            },
        };

        var yaml = serializer.Serialize(writableConfig);
        return yaml.EndsWith(Environment.NewLine, StringComparison.Ordinal)
            ? yaml
            : $"{yaml}{Environment.NewLine}";
    }

    private sealed class WritableAppConfig
    {
        public ImmichSettings Immich { get; set; } = new();

        public WritableWatchSettings Watch { get; set; } = new();

        public RetrySettings Retry { get; set; } = new();

        public LoggingSettings Logging { get; set; } = new();
    }

    private sealed class WritableWatchSettings
    {
        public List<WritableWatchSourceSettings> Sources { get; set; } = new();

        public int BatchIntervalSeconds { get; set; } = 5;

        public int MaxBatchSize { get; set; } = 25;

        public int FileReadyTimeoutSeconds { get; set; } = 30;
    }

    private sealed class WritableWatchSourceSettings
    {
        public string Path { get; set; } = string.Empty;

        public string AlbumName { get; set; } = string.Empty;

        public bool IncludeSubdirectories { get; set; }

        public List<string> Extensions { get; set; } = new();

        public List<string> ExcludeDirectories { get; set; } = new();

        public List<string> ExcludeFileNames { get; set; } = new();
    }
}
