using ImmichFolderWatch.Core.Interfaces;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace ImmichFolderWatch.Core.Configuration;

public sealed class AppConfigLoader : IAppConfigLoader
{
    public static AppConfig NormalizeForRuntime(AppConfig config, string configDirectory)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentException.ThrowIfNullOrWhiteSpace(configDirectory);

        var clone = Clone(config);
        Normalize(clone, Path.GetFullPath(configDirectory), normalizePaths: true);
        return clone;
    }

    public AppConfig Load(string configPath)
    {
        return LoadInternal(configPath, normalizePaths: true);
    }

    public AppConfig LoadForEditing(string configPath)
    {
        return LoadInternal(configPath, normalizePaths: false);
    }

    private AppConfig LoadInternal(string configPath, bool normalizePaths)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(configPath);

        var fullConfigPath = Path.GetFullPath(configPath);

        if (!File.Exists(fullConfigPath))
        {
            throw new FileNotFoundException($"Configuration file not found: {fullConfigPath}", fullConfigPath);
        }

        var yaml = File.ReadAllText(fullConfigPath);

        var deserializer = new DeserializerBuilder()
            .WithNamingConvention(CamelCaseNamingConvention.Instance)
            .IgnoreUnmatchedProperties()
            .Build();

        var config = deserializer.Deserialize<AppConfig>(yaml)
            ?? throw new InvalidOperationException("Configuration file could not be parsed into AppConfig.");

        Normalize(config, Path.GetDirectoryName(fullConfigPath) ?? AppContext.BaseDirectory, normalizePaths);
        return config;
    }

    private static AppConfig Clone(AppConfig config)
    {
        config.Immich ??= new ImmichSettings();
        config.Watch ??= new WatchSettings();
        config.Retry ??= new RetrySettings();
        config.Logging ??= new LoggingSettings();
        config.Watch.Sources ??= new List<WatchSourceSettings>();
        config.Watch.Extensions ??= new List<string>();

        return new AppConfig
        {
            Immich = new ImmichSettings
            {
                ServerApiUrl = config.Immich.ServerApiUrl,
                ApiKey = config.Immich.ApiKey,
            },
            Watch = new WatchSettings
            {
                Sources = config.Watch.Sources
                    .Where(source => source is not null)
                    .Select(source => new WatchSourceSettings
                    {
                        Path = source.Path,
                        AlbumName = source.AlbumName,
                        IncludeSubdirectories = source.IncludeSubdirectories,
                        Extensions = (source.Extensions ?? new List<string>()).ToList(),
                        ExcludeDirectories = (source.ExcludeDirectories ?? new List<string>()).ToList(),
                        ExcludeFileNames = (source.ExcludeFileNames ?? new List<string>()).ToList(),
                    })
                    .ToList(),
                Extensions = config.Watch.Extensions.ToList(),
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
    }

    private static void Normalize(AppConfig config, string configDirectory, bool normalizePaths)
    {
        config.Immich ??= new ImmichSettings();
        config.Watch ??= new WatchSettings();
        config.Retry ??= new RetrySettings();
        config.Logging ??= new LoggingSettings();

        config.Immich.ServerApiUrl = (config.Immich.ServerApiUrl ?? string.Empty).Trim();
        config.Immich.ApiKey = (config.Immich.ApiKey ?? string.Empty).Trim();

        config.Watch.Sources ??= new List<WatchSourceSettings>();
        config.Watch.Extensions ??= new List<string>();
        var legacyExtensions = NormalizeExtensions(config.Watch.Extensions);

        config.Watch.Sources = config.Watch.Sources
            .Where(source => source is not null)
            .Select(source => new WatchSourceSettings
            {
                Path = NormalizePath(source.Path, configDirectory, normalizePaths),
                AlbumName = (source.AlbumName ?? string.Empty).Trim(),
                IncludeSubdirectories = source.IncludeSubdirectories,
                Extensions = GetSourceExtensions(source, legacyExtensions),
                ExcludeDirectories = NormalizePatterns(source.ExcludeDirectories),
                ExcludeFileNames = NormalizePatterns(source.ExcludeFileNames),
            })
            .ToList();

        config.Watch.Extensions = new List<string>();

        config.Logging.Level = (config.Logging.Level ?? "Information").Trim();
        config.Logging.LogDirectory = NormalizePath(
            string.IsNullOrWhiteSpace(config.Logging.LogDirectory) ? "logs" : config.Logging.LogDirectory,
            configDirectory,
            normalizePaths);
    }

    private static List<string> GetSourceExtensions(WatchSourceSettings source, IReadOnlyList<string> legacyExtensions)
    {
        var sourceExtensions = NormalizeExtensions(source.Extensions);
        if (sourceExtensions.Count > 0)
        {
            return sourceExtensions;
        }

        return legacyExtensions.Count > 0
            ? legacyExtensions.ToList()
            : new List<string>();
    }

    private static List<string> NormalizeExtensions(IEnumerable<string>? extensions)
    {
        return (extensions ?? Array.Empty<string>())
            .Where(extension => !string.IsNullOrWhiteSpace(extension))
            .Select(NormalizeExtension)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private static List<string> NormalizePatterns(IEnumerable<string>? values)
    {
        return (values ?? Array.Empty<string>())
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private static string NormalizeExtension(string extension)
    {
        var value = extension.Trim();
        return value.StartsWith('.')
            ? value.ToLowerInvariant()
            : $".{value.ToLowerInvariant()}";
    }

    private static string NormalizePath(string? path, string configDirectory, bool normalizePaths)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return string.Empty;
        }

        var trimmed = path.Trim();
        if (!normalizePaths)
        {
            return trimmed;
        }

        return Path.IsPathRooted(trimmed)
            ? Path.GetFullPath(trimmed)
            : Path.GetFullPath(Path.Combine(configDirectory, trimmed));
    }
}
