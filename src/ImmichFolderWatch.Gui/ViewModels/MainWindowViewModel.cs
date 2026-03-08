using System.Collections.ObjectModel;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Gui.Models;

namespace ImmichFolderWatch.Gui.ViewModels;

public sealed class MainWindowViewModel : BindableBase
{
    private string _immichServerApiUrl = string.Empty;
    private string _immichApiKey = string.Empty;
    private string _extensionsText = string.Empty;
    private string _batchIntervalSeconds = "5";
    private string _maxBatchSize = "25";
    private string _fileReadyTimeoutSeconds = "30";
    private string _retryMaxAttempts = "5";
    private string _retryBaseDelayMilliseconds = "500";
    private string _loggingLevel = "Information";
    private string _logDirectory = GetDefaultLogDirectory();
    private string _statusHeadline = "Loading current service status...";
    private string _statusDetails = string.Empty;
    private string _operationMessage = string.Empty;

    public MainWindowViewModel()
    {
        Sources.Add(new WatchSourceItem());
    }

    public ObservableCollection<WatchSourceItem> Sources { get; } = new();

    public string[] AvailableLogLevels { get; } =
    {
        "Trace",
        "Debug",
        "Information",
        "Warning",
        "Error",
        "Critical",
    };

    public string ImmichServerApiUrl
    {
        get => _immichServerApiUrl;
        set => SetProperty(ref _immichServerApiUrl, value);
    }

    public string ImmichApiKey
    {
        get => _immichApiKey;
        set => SetProperty(ref _immichApiKey, value);
    }

    public string ExtensionsText
    {
        get => _extensionsText;
        set => SetProperty(ref _extensionsText, value);
    }

    public string BatchIntervalSeconds
    {
        get => _batchIntervalSeconds;
        set => SetProperty(ref _batchIntervalSeconds, value);
    }

    public string MaxBatchSize
    {
        get => _maxBatchSize;
        set => SetProperty(ref _maxBatchSize, value);
    }

    public string FileReadyTimeoutSeconds
    {
        get => _fileReadyTimeoutSeconds;
        set => SetProperty(ref _fileReadyTimeoutSeconds, value);
    }

    public string RetryMaxAttempts
    {
        get => _retryMaxAttempts;
        set => SetProperty(ref _retryMaxAttempts, value);
    }

    public string RetryBaseDelayMilliseconds
    {
        get => _retryBaseDelayMilliseconds;
        set => SetProperty(ref _retryBaseDelayMilliseconds, value);
    }

    public string LoggingLevel
    {
        get => _loggingLevel;
        set => SetProperty(ref _loggingLevel, value);
    }

    public string LogDirectory
    {
        get => _logDirectory;
        set => SetProperty(ref _logDirectory, value);
    }

    public string StatusHeadline
    {
        get => _statusHeadline;
        set => SetProperty(ref _statusHeadline, value);
    }

    public string StatusDetails
    {
        get => _statusDetails;
        set => SetProperty(ref _statusDetails, value);
    }

    public string OperationMessage
    {
        get => _operationMessage;
        set => SetProperty(ref _operationMessage, value);
    }

    public void Load(AppConfig config)
    {
        ArgumentNullException.ThrowIfNull(config);

        ImmichServerApiUrl = config.Immich.ServerApiUrl;
        ImmichApiKey = config.Immich.ApiKey;
        ExtensionsText = string.Join(Environment.NewLine, config.Watch.Extensions);
        BatchIntervalSeconds = config.Watch.BatchIntervalSeconds.ToString();
        MaxBatchSize = config.Watch.MaxBatchSize.ToString();
        FileReadyTimeoutSeconds = config.Watch.FileReadyTimeoutSeconds.ToString();
        RetryMaxAttempts = config.Retry.MaxAttempts.ToString();
        RetryBaseDelayMilliseconds = config.Retry.BaseDelayMilliseconds.ToString();
        LoggingLevel = string.IsNullOrWhiteSpace(config.Logging.Level) ? "Information" : config.Logging.Level;
        LogDirectory = string.IsNullOrWhiteSpace(config.Logging.LogDirectory) ? GetDefaultLogDirectory() : config.Logging.LogDirectory;

        Sources.Clear();
        foreach (var source in config.Watch.Sources)
        {
            Sources.Add(new WatchSourceItem
            {
                Path = source.Path,
                AlbumName = source.AlbumName,
                IncludeSubdirectories = source.IncludeSubdirectories,
            });
        }

        if (Sources.Count == 0)
        {
            Sources.Add(new WatchSourceItem());
        }
    }

    public bool TryCreateConfig(out AppConfig config, out IReadOnlyList<string> errors)
    {
        var errorList = new List<string>();

        var batchIntervalSeconds = ParsePositiveInteger(BatchIntervalSeconds, "watch.batchIntervalSeconds", errorList);
        var maxBatchSize = ParsePositiveInteger(MaxBatchSize, "watch.maxBatchSize", errorList);
        var fileReadyTimeoutSeconds = ParsePositiveInteger(FileReadyTimeoutSeconds, "watch.fileReadyTimeoutSeconds", errorList);
        var retryMaxAttempts = ParsePositiveInteger(RetryMaxAttempts, "retry.maxAttempts", errorList);
        var retryBaseDelayMilliseconds = ParsePositiveInteger(RetryBaseDelayMilliseconds, "retry.baseDelayMilliseconds", errorList);
        var logDirectory = LogDirectory.Trim();

        if (string.IsNullOrWhiteSpace(logDirectory))
        {
            errorList.Add("logging.logDirectory is required.");
        }
        else if (!Path.IsPathFullyQualified(logDirectory))
        {
            errorList.Add("logging.logDirectory must be an absolute path.");
        }

        config = new AppConfig
        {
            Immich = new ImmichSettings
            {
                ServerApiUrl = ImmichServerApiUrl.Trim(),
                ApiKey = ImmichApiKey.Trim(),
            },
            Watch = new WatchSettings
            {
                Sources = Sources.Select(source => new WatchSourceSettings
                {
                    Path = source.Path.Trim(),
                    AlbumName = source.AlbumName.Trim(),
                    IncludeSubdirectories = source.IncludeSubdirectories,
                }).ToList(),
                Extensions = ParseExtensions(ExtensionsText).ToList(),
                BatchIntervalSeconds = batchIntervalSeconds,
                MaxBatchSize = maxBatchSize,
                FileReadyTimeoutSeconds = fileReadyTimeoutSeconds,
            },
            Retry = new RetrySettings
            {
                MaxAttempts = retryMaxAttempts,
                BaseDelayMilliseconds = retryBaseDelayMilliseconds,
            },
            Logging = new LoggingSettings
            {
                Level = LoggingLevel.Trim(),
                LogDirectory = logDirectory,
            },
        };

        errors = errorList;
        return errorList.Count == 0;
    }

    public string GetEffectiveLogDirectory()
    {
        return LogDirectory.Trim();
    }

    private static int ParsePositiveInteger(string value, string fieldName, List<string> errors)
    {
        if (!int.TryParse(value, out var parsedValue))
        {
            errors.Add($"{fieldName} must be a whole number.");
            return 0;
        }

        if (parsedValue <= 0)
        {
            errors.Add($"{fieldName} must be greater than zero.");
        }

        return parsedValue;
    }

    private static IEnumerable<string> ParseExtensions(string value)
    {
        return value
            .Split(['\r', '\n', ',', ';'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(extension => !string.IsNullOrWhiteSpace(extension));
    }

    private static string GetDefaultLogDirectory()
    {
        return Path.GetFullPath(InstallationPaths.GetLogDirectory(AppContext.BaseDirectory));
    }
}
