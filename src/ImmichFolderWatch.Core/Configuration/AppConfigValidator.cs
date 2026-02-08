namespace ImmichFolderWatch.Core.Configuration;

public static class AppConfigValidator
{
    public static IReadOnlyList<string> Validate(AppConfig config)
    {
        ArgumentNullException.ThrowIfNull(config);

        var errors = new List<string>();

        ValidateImmich(config, errors);
        ValidateWatch(config, errors);
        ValidateRetry(config, errors);
        ValidateLogging(config, errors);

        return errors;
    }

    public static string EnsureTrailingSlash(string value)
    {
        return value.EndsWith('/') ? value : $"{value}/";
    }

    private static void ValidateImmich(AppConfig config, List<string> errors)
    {
        if (string.IsNullOrWhiteSpace(config.Immich.ServerApiUrl))
        {
            errors.Add("immich.serverApiUrl is required.");
        }
        else if (!Uri.TryCreate(config.Immich.ServerApiUrl, UriKind.Absolute, out var uri))
        {
            errors.Add("immich.serverApiUrl must be a valid absolute URL.");
        }
        else
        {
            var normalizedPath = uri.AbsolutePath.TrimEnd('/');
            if (!normalizedPath.EndsWith("/api", StringComparison.OrdinalIgnoreCase))
            {
                errors.Add("immich.serverApiUrl must include '/api' at the end of the path.");
            }
        }

        if (string.IsNullOrWhiteSpace(config.Immich.ApiKey))
        {
            errors.Add("immich.apiKey is required.");
        }
    }

    private static void ValidateWatch(AppConfig config, List<string> errors)
    {
        if (config.Watch.Sources.Count == 0)
        {
            errors.Add("watch.sources must contain at least one source.");
        }

        for (var i = 0; i < config.Watch.Sources.Count; i++)
        {
            var source = config.Watch.Sources[i];

            if (string.IsNullOrWhiteSpace(source.Path))
            {
                errors.Add($"watch.sources[{i}].path is required.");
            }
            else if (!Directory.Exists(source.Path))
            {
                errors.Add($"watch.sources[{i}].path does not exist: {source.Path}");
            }

            if (string.IsNullOrWhiteSpace(source.AlbumName))
            {
                errors.Add($"watch.sources[{i}].albumName is required.");
            }
        }

        if (config.Watch.Extensions.Count == 0)
        {
            errors.Add("watch.extensions must contain at least one file extension.");
        }

        if (config.Watch.BatchIntervalSeconds <= 0)
        {
            errors.Add("watch.batchIntervalSeconds must be greater than zero.");
        }

        if (config.Watch.MaxBatchSize <= 0)
        {
            errors.Add("watch.maxBatchSize must be greater than zero.");
        }

        if (config.Watch.FileReadyTimeoutSeconds <= 0)
        {
            errors.Add("watch.fileReadyTimeoutSeconds must be greater than zero.");
        }
    }

    private static void ValidateRetry(AppConfig config, List<string> errors)
    {
        if (config.Retry.MaxAttempts <= 0)
        {
            errors.Add("retry.maxAttempts must be greater than zero.");
        }

        if (config.Retry.BaseDelayMilliseconds <= 0)
        {
            errors.Add("retry.baseDelayMilliseconds must be greater than zero.");
        }
    }

    private static void ValidateLogging(AppConfig config, List<string> errors)
    {
        if (string.IsNullOrWhiteSpace(config.Logging.Level))
        {
            errors.Add("logging.level is required.");
        }

        if (string.IsNullOrWhiteSpace(config.Logging.LogDirectory))
        {
            errors.Add("logging.logDirectory is required.");
        }
    }
}
