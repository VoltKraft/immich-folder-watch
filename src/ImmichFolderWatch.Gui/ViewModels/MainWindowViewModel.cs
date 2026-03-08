using System.Collections.ObjectModel;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Gui.Models;

namespace ImmichFolderWatch.Gui.ViewModels;

public sealed class MainWindowViewModel : BindableBase
{
    private const string ShowApiKeyToolTipText = "Show API key";
    private const string HideApiKeyToolTipText = "Hide API key";

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
    private string _serviceBadgeText = "Loading";
    private string _serviceBadgeBackground = "#D7E8FF";
    private string _productVersionText = string.Empty;
    private string _operationMessage = string.Empty;
    private string _saveActionButtonText = "Save and Start";
    private string _immichUrlStatusText = "Not checked";
    private string _immichUrlStatusBackground = "#E0E3E8";
    private string _immichApiKeyStatusText = "Not checked";
    private string _immichApiKeyStatusBackground = "#E0E3E8";
    private string _immichPermissionsStatusText = "Not checked";
    private string _immichPermissionsStatusBackground = "#E0E3E8";
    private bool _revealImmichApiKey;
    private bool _shouldMaskImmichApiKey;
    private bool _showPlainImmichApiKeyInput = true;
    private bool _showImmichApiKeyRevealButton;
    private bool _isImmichApiKeyPlaceholder;
    private string _immichApiKeyRevealToolTip = ShowApiKeyToolTipText;
    private bool _showStartServiceButton;
    private bool _showStopServiceButton;
    private bool _showRestartServiceButton;

    public MainWindowViewModel()
    {
        Sources.Add(new WatchSourceItem());
        RefreshImmichApiKeyPresentation(resetVisibleState: true);
        ResetImmichCheckStatus();
    }

    public ObservableCollection<WatchSourceItem> Sources { get; } = new();

    public ObservableCollection<ImmichPermissionStatusItem> ImmichPermissionStatuses { get; } = new();

    public string[] AvailableLogLevels { get; } =
    {
        "Trace",
        "Debug",
        "Information",
        "Warning",
        "Error",
        "Critical",
    };

    public string ImmichApiKeyPlaceholderText { get; } = AppConfigValidator.ExampleApiKeyPlaceholder;

    public string ImmichServerApiUrl
    {
        get => _immichServerApiUrl;
        set
        {
            if (SetProperty(ref _immichServerApiUrl, value))
            {
                ResetImmichCheckStatus();
            }
        }
    }

    public string ImmichApiKey
    {
        get => _immichApiKey;
        set
        {
            var wasPlaceholder = IsExampleApiKeyPlaceholder(_immichApiKey);
            if (SetProperty(ref _immichApiKey, value))
            {
                RefreshImmichApiKeyPresentation(resetVisibleState: wasPlaceholder);
                ResetImmichCheckStatus();
            }
        }
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

    public string ServiceBadgeText
    {
        get => _serviceBadgeText;
        set => SetProperty(ref _serviceBadgeText, value);
    }

    public string ServiceBadgeBackground
    {
        get => _serviceBadgeBackground;
        set => SetProperty(ref _serviceBadgeBackground, value);
    }

    public string OperationMessage
    {
        get => _operationMessage;
        set => SetProperty(ref _operationMessage, value);
    }

    public string ProductVersionText
    {
        get => _productVersionText;
        set => SetProperty(ref _productVersionText, value);
    }

    public string SaveActionButtonText
    {
        get => _saveActionButtonText;
        set => SetProperty(ref _saveActionButtonText, value);
    }

    public string ImmichUrlStatusText
    {
        get => _immichUrlStatusText;
        set => SetProperty(ref _immichUrlStatusText, value);
    }

    public string ImmichUrlStatusBackground
    {
        get => _immichUrlStatusBackground;
        set => SetProperty(ref _immichUrlStatusBackground, value);
    }

    public string ImmichApiKeyStatusText
    {
        get => _immichApiKeyStatusText;
        set => SetProperty(ref _immichApiKeyStatusText, value);
    }

    public string ImmichApiKeyStatusBackground
    {
        get => _immichApiKeyStatusBackground;
        set => SetProperty(ref _immichApiKeyStatusBackground, value);
    }

    public string ImmichPermissionsStatusText
    {
        get => _immichPermissionsStatusText;
        set => SetProperty(ref _immichPermissionsStatusText, value);
    }

    public string ImmichPermissionsStatusBackground
    {
        get => _immichPermissionsStatusBackground;
        set => SetProperty(ref _immichPermissionsStatusBackground, value);
    }

    public bool RevealImmichApiKey
    {
        get => _revealImmichApiKey;
        private set => SetProperty(ref _revealImmichApiKey, value);
    }

    public bool ShouldMaskImmichApiKey
    {
        get => _shouldMaskImmichApiKey;
        private set => SetProperty(ref _shouldMaskImmichApiKey, value);
    }

    public bool ShowPlainImmichApiKeyInput
    {
        get => _showPlainImmichApiKeyInput;
        private set => SetProperty(ref _showPlainImmichApiKeyInput, value);
    }

    public bool ShowImmichApiKeyRevealButton
    {
        get => _showImmichApiKeyRevealButton;
        private set => SetProperty(ref _showImmichApiKeyRevealButton, value);
    }

    public bool IsImmichApiKeyPlaceholder
    {
        get => _isImmichApiKeyPlaceholder;
        private set => SetProperty(ref _isImmichApiKeyPlaceholder, value);
    }

    public string ImmichApiKeyRevealToolTip
    {
        get => _immichApiKeyRevealToolTip;
        private set => SetProperty(ref _immichApiKeyRevealToolTip, value);
    }

    public bool ShowStartServiceButton
    {
        get => _showStartServiceButton;
        set => SetProperty(ref _showStartServiceButton, value);
    }

    public bool ShowStopServiceButton
    {
        get => _showStopServiceButton;
        set => SetProperty(ref _showStopServiceButton, value);
    }

    public bool ShowRestartServiceButton
    {
        get => _showRestartServiceButton;
        set => SetProperty(ref _showRestartServiceButton, value);
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

        RefreshImmichApiKeyPresentation(resetVisibleState: true);
        ResetImmichCheckStatus();
    }

    public void ToggleImmichApiKeyVisibility()
    {
        if (!ShowImmichApiKeyRevealButton)
        {
            return;
        }

        RevealImmichApiKey = !RevealImmichApiKey;
        RefreshImmichApiKeyPresentation(resetVisibleState: false);
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

    public AppConfig CreateImmichCheckConfig()
    {
        return new AppConfig
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
            },
            Retry = new RetrySettings
            {
                MaxAttempts = 1,
                BaseDelayMilliseconds = 250,
            },
            Logging = new LoggingSettings
            {
                Level = "Information",
                LogDirectory = GetDefaultLogDirectory(),
            },
        };
    }

    public void SetImmichCheckInProgress()
    {
        SetImmichUrlStatus(CheckState.Checking);
        SetImmichApiKeyStatus(CheckState.Checking);
        SetImmichPermissionsStatus(CheckState.Checking);

        RefreshPermissionStatuses(CreatePermissionItems(
            new[]
            {
                new ImmichPermissionCheckResult { DisplayName = "Asset Upload", PermissionName = "asset.upload", State = CheckState.Checking, Message = "Checking...", BlocksConfigVerification = true },
                new ImmichPermissionCheckResult { DisplayName = "Album Read", PermissionName = "album.read", State = CheckState.Checking, Message = "Checking..." },
                new ImmichPermissionCheckResult { DisplayName = "Album Create", PermissionName = "album.create", State = CheckState.Checking, Message = "Checking..." },
                new ImmichPermissionCheckResult { DisplayName = "Add Asset To Album", PermissionName = "albumAsset.create", State = CheckState.Checking, Message = "Checking..." },
            }));
    }

    public void ApplyImmichCheckResult(ImmichAccessCheckResult result)
    {
        ArgumentNullException.ThrowIfNull(result);

        SetImmichUrlStatus(result.UrlState);
        SetImmichApiKeyStatus(result.ApiKeyState);
        SetImmichPermissionsStatus(result.PermissionsState);

        RefreshPermissionStatuses(CreatePermissionItems(result.PermissionResults));
    }

    public void ApplyServiceActionVisibility(ServiceStatusSnapshot? status)
    {
        var showStart = status is { Exists: true, State: ServiceRunState.Stopped };
        var showStop = status is { Exists: true, State: ServiceRunState.Running };
        var showRestart = status is { Exists: true, State: ServiceRunState.Running };

        ShowStartServiceButton = showStart;
        ShowStopServiceButton = showStop;
        ShowRestartServiceButton = showRestart;
        SaveActionButtonText = status is { State: ServiceRunState.Running }
            ? "Save and Restart"
            : "Save and Start";
    }

    private void ResetImmichCheckStatus()
    {
        SetImmichUrlStatus(CheckState.NotChecked);
        SetImmichApiKeyStatus(CheckState.NotChecked);
        SetImmichPermissionsStatus(CheckState.NotChecked);

        RefreshPermissionStatuses(CreatePermissionItems(
            new[]
            {
                new ImmichPermissionCheckResult { DisplayName = "Asset Upload", PermissionName = "asset.upload", State = CheckState.NotChecked, Message = "Not checked yet.", BlocksConfigVerification = true },
                new ImmichPermissionCheckResult { DisplayName = "Album Read", PermissionName = "album.read", State = CheckState.NotChecked, Message = "Not checked yet." },
                new ImmichPermissionCheckResult { DisplayName = "Album Create", PermissionName = "album.create", State = CheckState.NotChecked, Message = "Not checked yet." },
                new ImmichPermissionCheckResult { DisplayName = "Add Asset To Album", PermissionName = "albumAsset.create", State = CheckState.NotChecked, Message = "Not checked yet." },
            }));
    }

    private void SetImmichUrlStatus(CheckState state)
    {
        ImmichUrlStatusText = GetCheckStateText(state);
        ImmichUrlStatusBackground = GetCheckStateBackground(state);
    }

    private void SetImmichApiKeyStatus(CheckState state)
    {
        ImmichApiKeyStatusText = GetCheckStateText(state);
        ImmichApiKeyStatusBackground = GetCheckStateBackground(state);
    }

    private void SetImmichPermissionsStatus(CheckState state)
    {
        ImmichPermissionsStatusText = GetCheckStateText(state);
        ImmichPermissionsStatusBackground = GetCheckStateBackground(state);
    }

    private void RefreshPermissionStatuses(IEnumerable<ImmichPermissionStatusItem> items)
    {
        ImmichPermissionStatuses.Clear();
        foreach (var item in items)
        {
            ImmichPermissionStatuses.Add(item);
        }
    }

    private static IEnumerable<ImmichPermissionStatusItem> CreatePermissionItems(IEnumerable<ImmichPermissionCheckResult> results)
    {
        return results.Select(result => new ImmichPermissionStatusItem
        {
            DisplayName = result.DisplayName,
            PermissionName = result.PermissionName,
            StatusText = GetCheckStateText(result.State),
            StatusBackground = GetCheckStateBackground(result.State),
            Message = result.Message,
        });
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

    private void RefreshImmichApiKeyPresentation(bool resetVisibleState)
    {
        if (resetVisibleState)
        {
            RevealImmichApiKey = false;
        }

        var trimmedApiKey = (_immichApiKey ?? string.Empty).Trim();
        var isPlaceholder = IsExampleApiKeyPlaceholder(trimmedApiKey);
        var hasRealKey = !string.IsNullOrWhiteSpace(trimmedApiKey) && !isPlaceholder;
        var revealPassword = isPlaceholder || RevealImmichApiKey;

        IsImmichApiKeyPlaceholder = isPlaceholder;
        ShowImmichApiKeyRevealButton = hasRealKey;
        ShouldMaskImmichApiKey = hasRealKey && !revealPassword;
        ShowPlainImmichApiKeyInput = !ShouldMaskImmichApiKey;
        RevealImmichApiKey = revealPassword;
        ImmichApiKeyRevealToolTip = revealPassword ? HideApiKeyToolTipText : ShowApiKeyToolTipText;
    }

    private static bool IsExampleApiKeyPlaceholder(string? value)
    {
        return string.Equals(
            (value ?? string.Empty).Trim(),
            AppConfigValidator.ExampleApiKeyPlaceholder,
            StringComparison.Ordinal);
    }

    private static string GetCheckStateText(CheckState state)
    {
        return state switch
        {
            CheckState.Passed => "OK",
            CheckState.Warning => "Warning",
            CheckState.Failed => "Failed",
            CheckState.Checking => "Checking",
            _ => "Not checked",
        };
    }

    private static string GetCheckStateBackground(CheckState state)
    {
        return state switch
        {
            CheckState.Passed => "#D8F0D9",
            CheckState.Warning => "#F9E3B4",
            CheckState.Failed => "#F3C7C2",
            CheckState.Checking => "#D7E8FF",
            _ => "#E0E3E8",
        };
    }
}
