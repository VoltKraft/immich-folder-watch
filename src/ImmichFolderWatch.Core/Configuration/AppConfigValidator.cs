namespace ImmichFolderWatch.Core.Configuration;

public static class AppConfigValidator
{
    public const string ExampleApiKeyPlaceholder = "REPLACE_WITH_IMMICH_API_KEY";

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

    public static string? ValidateServerApiUrl(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "immich.serverApiUrl is required.";
        }

        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri))
        {
            return "immich.serverApiUrl must be a valid absolute URL.";
        }

        var normalizedPath = uri.AbsolutePath.TrimEnd('/');
        return normalizedPath.EndsWith("/api", StringComparison.OrdinalIgnoreCase)
            ? null
            : "immich.serverApiUrl must include '/api' at the end of the path.";
    }

    public static string? ValidateApiKey(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "immich.apiKey is required.";
        }

        return string.Equals(value.Trim(), ExampleApiKeyPlaceholder, StringComparison.Ordinal)
            ? "immich.apiKey must be replaced with a real Immich API key."
            : null;
    }

    private static void ValidateImmich(AppConfig config, List<string> errors)
    {
        var apiUrlError = ValidateServerApiUrl(config.Immich.ServerApiUrl);
        if (!string.IsNullOrWhiteSpace(apiUrlError))
        {
            errors.Add(apiUrlError);
        }

        var apiKeyError = ValidateApiKey(config.Immich.ApiKey);
        if (!string.IsNullOrWhiteSpace(apiKeyError))
        {
            errors.Add(apiKeyError);
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

            if ((source.Extensions?.Count ?? 0) == 0)
            {
                errors.Add($"watch.sources[{i}].extensions must contain at least one file extension.");
            }
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

        if (!LogTargets.IsFile(config.Logging.Target))
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(config.Logging.LogDirectory))
        {
            errors.Add("logging.logDirectory is required when logging.target is 'file'.");
        }
        else if (!Path.IsPathFullyQualified(config.Logging.LogDirectory))
        {
            errors.Add("logging.logDirectory must be an absolute path.");
        }
    }
}
