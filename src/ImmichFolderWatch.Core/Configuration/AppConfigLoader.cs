using ImmichFolderWatch.Core.Interfaces;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace ImmichFolderWatch.Core.Configuration;

public sealed class AppConfigLoader : IAppConfigLoader
{
    public AppConfig Load(string configPath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(configPath);

        if (!File.Exists(configPath))
        {
            throw new FileNotFoundException($"Configuration file not found: {configPath}", configPath);
        }

        var yaml = File.ReadAllText(configPath);

        var deserializer = new DeserializerBuilder()
            .WithNamingConvention(CamelCaseNamingConvention.Instance)
            .IgnoreUnmatchedProperties()
            .Build();

        var config = deserializer.Deserialize<AppConfig>(yaml)
            ?? throw new InvalidOperationException("Configuration file could not be parsed into AppConfig.");

        Normalize(config);
        return config;
    }

    private static void Normalize(AppConfig config)
    {
        config.Immich ??= new ImmichSettings();
        config.Watch ??= new WatchSettings();
        config.Retry ??= new RetrySettings();
        config.Logging ??= new LoggingSettings();

        config.Immich.ServerApiUrl = (config.Immich.ServerApiUrl ?? string.Empty).Trim();
        config.Immich.ApiKey = (config.Immich.ApiKey ?? string.Empty).Trim();

        config.Watch.Sources ??= new List<WatchSourceSettings>();
        config.Watch.Extensions ??= new List<string>();

        config.Watch.Sources = config.Watch.Sources
            .Where(source => source is not null)
            .Select(source => new WatchSourceSettings
            {
                Path = (source.Path ?? string.Empty).Trim(),
                AlbumName = (source.AlbumName ?? string.Empty).Trim(),
                IncludeSubdirectories = source.IncludeSubdirectories,
            })
            .ToList();

        config.Watch.Extensions = config.Watch.Extensions
            .Where(extension => !string.IsNullOrWhiteSpace(extension))
            .Select(NormalizeExtension)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        config.Logging.Level = (config.Logging.Level ?? "Information").Trim();
        config.Logging.LogDirectory = string.IsNullOrWhiteSpace(config.Logging.LogDirectory)
            ? "logs"
            : config.Logging.LogDirectory.Trim();
    }

    private static string NormalizeExtension(string extension)
    {
        var value = extension.Trim();
        return value.StartsWith('.')
            ? value.ToLowerInvariant()
            : $".{value.ToLowerInvariant()}";
    }
}
