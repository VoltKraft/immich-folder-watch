using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using Avalonia.Threading;
using ImmichFolderWatch.App.Models;
using ImmichFolderWatch.App.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.App.ViewModels;

public sealed class MainWindowViewModel : BindableBase
{
    private const string ShowApiKeyToolTipText = "Show API key";
    private const string HideApiKeyToolTipText = "Hide API key";
    private static readonly string[] DefaultImageExtensions =
    {
        ".avif",
        ".bmp",
        ".gif",
        ".heic",
        ".heif",
        ".jp2",
        ".jpe",
        ".jpeg",
        ".jpg",
        ".insp",
        ".jxl",
        ".png",
        ".psd",
        ".raw",
        ".rw2",
        ".svg",
        ".tif",
        ".tiff",
        ".webp",
    };

    private readonly SyncStatusProvider _syncStatusProvider;
    private readonly AutostartManager _autostartManager;
    private bool _suppressAutostartWrite;

    private string _immichServerApiUrl = string.Empty;
    private string _immichApiKey = string.Empty;
    private string _batchIntervalSeconds = "5";
    private string _maxBatchSize = "25";
    private string _fileReadyTimeoutSeconds = "30";
    private string _retryMaxAttempts = "5";
    private string _retryBaseDelayMilliseconds = "500";
    private string _loggingLevel = "Information";
    private string _logDirectory = GetDefaultLogDirectory();
    private string _statusHeadline = "Immich Folder Watch läuft im Hintergrund.";
    private string _statusDetails = string.Empty;
    private string _syncStatusBadgeText = "Bereit";
    private StatusTone _syncStatusBadgeTone = StatusTone.Neutral;
    private string _serverConnectionText = "Unbekannt";
    private StatusTone _serverConnectionTone = StatusTone.Neutral;
    private string _serverConnectionDetail = string.Empty;
    private string _lastSyncText = "Noch kein Sync durchgeführt.";
    private string _currentUploadText = "Aktuell kein Upload.";
    private string _pendingCountText = "0";
    private bool _autostartEnabled;
    private string _productVersionText = string.Empty;
    private string _operationMessage = string.Empty;
    private string _saveActionButtonText = "Speichern und Anwenden";
    private string _immichUrlStatusText = "Not checked";
    private StatusTone _immichUrlStatusTone = StatusTone.Neutral;
    private string _immichApiKeyStatusText = "Not checked";
    private StatusTone _immichApiKeyStatusTone = StatusTone.Neutral;
    private string _immichPermissionsStatusText = "Not checked";
    private StatusTone _immichPermissionsStatusTone = StatusTone.Neutral;
    private bool _revealImmichApiKey;
    private bool _shouldMaskImmichApiKey;
    private bool _showPlainImmichApiKeyInput = true;
    private bool _showImmichApiKeyRevealButton;
    private bool _isImmichApiKeyPlaceholder;
    private string _immichApiKeyRevealToolTip = ShowApiKeyToolTipText;

    public MainWindowViewModel(SyncStatusProvider syncStatusProvider, AutostartManager autostartManager)
    {
        _syncStatusProvider = syncStatusProvider ?? throw new ArgumentNullException(nameof(syncStatusProvider));
        _autostartManager = autostartManager ?? throw new ArgumentNullException(nameof(autostartManager));

        AddSource();
        RefreshImmichApiKeyPresentation(resetVisibleState: true);
        ResetImmichCheckStatus();

        _suppressAutostartWrite = true;
        AutostartEnabled = _autostartManager.IsEnabled();
        _suppressAutostartWrite = false;

        RefreshSyncStatusFromProvider();
        _syncStatusProvider.PropertyChanged += SyncStatusProvider_PropertyChanged;
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

    public string SyncStatusBadgeText
    {
        get => _syncStatusBadgeText;
        set => SetProperty(ref _syncStatusBadgeText, value);
    }

    public StatusTone SyncStatusBadgeTone
    {
        get => _syncStatusBadgeTone;
        set => SetProperty(ref _syncStatusBadgeTone, value);
    }

    public string ServerConnectionText
    {
        get => _serverConnectionText;
        set => SetProperty(ref _serverConnectionText, value);
    }

    public StatusTone ServerConnectionTone
    {
        get => _serverConnectionTone;
        set => SetProperty(ref _serverConnectionTone, value);
    }

    public string ServerConnectionDetail
    {
        get => _serverConnectionDetail;
        set => SetProperty(ref _serverConnectionDetail, value);
    }

    public string LastSyncText
    {
        get => _lastSyncText;
        set => SetProperty(ref _lastSyncText, value);
    }

    public string CurrentUploadText
    {
        get => _currentUploadText;
        set => SetProperty(ref _currentUploadText, value);
    }

    public string PendingCountText
    {
        get => _pendingCountText;
        set => SetProperty(ref _pendingCountText, value);
    }

    public bool AutostartEnabled
    {
        get => _autostartEnabled;
        set
        {
            if (!SetProperty(ref _autostartEnabled, value))
            {
                return;
            }

            if (_suppressAutostartWrite)
            {
                return;
            }

            ApplyAutostartChange(value);
        }
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

    public StatusTone ImmichUrlStatusTone
    {
        get => _immichUrlStatusTone;
        set => SetProperty(ref _immichUrlStatusTone, value);
    }

    public string ImmichApiKeyStatusText
    {
        get => _immichApiKeyStatusText;
        set => SetProperty(ref _immichApiKeyStatusText, value);
    }

    public StatusTone ImmichApiKeyStatusTone
    {
        get => _immichApiKeyStatusTone;
        set => SetProperty(ref _immichApiKeyStatusTone, value);
    }

    public string ImmichPermissionsStatusText
    {
        get => _immichPermissionsStatusText;
        set => SetProperty(ref _immichPermissionsStatusText, value);
    }

    public StatusTone ImmichPermissionsStatusTone
    {
        get => _immichPermissionsStatusTone;
        set => SetProperty(ref _immichPermissionsStatusTone, value);
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

    public void AddSource()
    {
        Sources.Add(CreateDefaultSource());
    }

    public void Load(AppConfig config)
    {
        ArgumentNullException.ThrowIfNull(config);

        ImmichServerApiUrl = config.Immich.ServerApiUrl;
        ImmichApiKey = config.Immich.ApiKey;
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
                ExtensionsText = string.Join(Environment.NewLine, source.Extensions),
                ExcludeDirectoriesText = string.Join(Environment.NewLine, source.ExcludeDirectories),
                ExcludeFileNamesText = string.Join(Environment.NewLine, source.ExcludeFileNames),
                ShowAdvancedOptions = false,
            });
        }

        if (Sources.Count == 0)
        {
            AddSource();
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
                    Extensions = ParseListInput(source.ExtensionsText).ToList(),
                    ExcludeDirectories = ParseListInput(source.ExcludeDirectoriesText).ToList(),
                    ExcludeFileNames = ParseListInput(source.ExcludeFileNamesText).ToList(),
                }).ToList(),
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
                    Extensions = ParseListInput(source.ExtensionsText).ToList(),
                    ExcludeDirectories = ParseListInput(source.ExcludeDirectoriesText).ToList(),
                    ExcludeFileNames = ParseListInput(source.ExcludeFileNamesText).ToList(),
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

    public void RefreshAutostartFromDisk()
    {
        _suppressAutostartWrite = true;
        try
        {
            AutostartEnabled = _autostartManager.IsEnabled();
        }
        finally
        {
            _suppressAutostartWrite = false;
        }
    }

    private void ApplyAutostartChange(bool enabled)
    {
        try
        {
            if (enabled)
            {
                _autostartManager.Enable();
            }
            else
            {
                _autostartManager.Disable();
            }
        }
        catch (Exception ex)
        {
            OperationMessage = $"Autostart konnte nicht aktualisiert werden: {ex.Message}";
            _suppressAutostartWrite = true;
            try
            {
                AutostartEnabled = _autostartManager.IsEnabled();
            }
            finally
            {
                _suppressAutostartWrite = false;
            }
        }
    }

    private void SyncStatusProvider_PropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (Dispatcher.UIThread.CheckAccess())
        {
            RefreshSyncStatusFromProvider();
        }
        else
        {
            Dispatcher.UIThread.Post(RefreshSyncStatusFromProvider);
        }
    }

    private void RefreshSyncStatusFromProvider()
    {
        switch (_syncStatusProvider.ServerConnection)
        {
            case ServerConnectionState.Ok:
                ServerConnectionText = "OK";
                break;
            case ServerConnectionState.Error:
                ServerConnectionText = "Fehler";
                break;
            case ServerConnectionState.Checking:
                ServerConnectionText = "Prüfe…";
                break;
            default:
                ServerConnectionText = "Unbekannt";
                break;
        }

        ServerConnectionTone = StatusToneMapper.FromServerConnection(_syncStatusProvider.ServerConnection);

        if (_syncStatusProvider.ServerConnection == ServerConnectionState.Error
            && !string.IsNullOrWhiteSpace(_syncStatusProvider.LastErrorMessage))
        {
            ServerConnectionDetail = _syncStatusProvider.LastErrorMessage!;
        }
        else if (_syncStatusProvider.LastServerCheckUtc.HasValue)
        {
            var check = _syncStatusProvider.LastServerCheckUtc.Value.ToLocalTime();
            ServerConnectionDetail = $"Zuletzt geprüft: {check:HH:mm:ss}";
        }
        else
        {
            ServerConnectionDetail = string.Empty;
        }

        LastSyncText = _syncStatusProvider.LastSyncCompletedUtc.HasValue
            ? _syncStatusProvider.LastSyncCompletedUtc.Value.ToLocalTime()
                .ToString("dd.MM.yyyy HH:mm:ss", CultureInfo.CurrentCulture)
            : "Noch kein Sync durchgeführt.";

        if (!string.IsNullOrWhiteSpace(_syncStatusProvider.CurrentlyUploadingFile))
        {
            var fileName = Path.GetFileName(_syncStatusProvider.CurrentlyUploadingFile);
            if (_syncStatusProvider.CurrentBatchSize > 0)
            {
                CurrentUploadText = $"{fileName} ({_syncStatusProvider.UploadedInCurrentBatch + 1}/{_syncStatusProvider.CurrentBatchSize})";
            }
            else
            {
                CurrentUploadText = fileName;
            }
        }
        else if (_syncStatusProvider.CurrentBatchSize > 0)
        {
            CurrentUploadText = $"Batch: {_syncStatusProvider.UploadedInCurrentBatch}/{_syncStatusProvider.CurrentBatchSize}";
        }
        else
        {
            CurrentUploadText = "Aktuell kein Upload.";
        }

        PendingCountText = _syncStatusProvider.PendingCount.ToString(CultureInfo.CurrentCulture);

        if (_syncStatusProvider.ServerConnection == ServerConnectionState.Error)
        {
            SyncStatusBadgeText = "Server offline";
            SyncStatusBadgeTone = StatusTone.Error;
        }
        else if (!string.IsNullOrWhiteSpace(_syncStatusProvider.CurrentlyUploadingFile)
                 || _syncStatusProvider.CurrentBatchSize > 0)
        {
            SyncStatusBadgeText = "Sync läuft";
            SyncStatusBadgeTone = StatusTone.Info;
        }
        else if (_syncStatusProvider.PendingCount > 0)
        {
            SyncStatusBadgeText = "Warteschlange";
            SyncStatusBadgeTone = StatusTone.Info;
        }
        else if (_syncStatusProvider.ServerConnection == ServerConnectionState.Ok)
        {
            SyncStatusBadgeText = "Bereit";
            SyncStatusBadgeTone = StatusTone.Success;
        }
        else
        {
            SyncStatusBadgeText = "Bereit";
            SyncStatusBadgeTone = StatusTone.Neutral;
        }
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
        ImmichUrlStatusTone = StatusToneMapper.FromCheckState(state);
    }

    private void SetImmichApiKeyStatus(CheckState state)
    {
        ImmichApiKeyStatusText = GetCheckStateText(state);
        ImmichApiKeyStatusTone = StatusToneMapper.FromCheckState(state);
    }

    private void SetImmichPermissionsStatus(CheckState state)
    {
        ImmichPermissionsStatusText = GetCheckStateText(state);
        ImmichPermissionsStatusTone = StatusToneMapper.FromCheckState(state);
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
            StatusTone = StatusToneMapper.FromCheckState(result.State),
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

    private static IEnumerable<string> ParseListInput(string value)
    {
        return value
            .Split(['\r', '\n', ',', ';'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(entry => !string.IsNullOrWhiteSpace(entry));
    }

    private static WatchSourceItem CreateDefaultSource()
    {
        return new WatchSourceItem
        {
            IncludeSubdirectories = false,
            ExtensionsText = string.Join(Environment.NewLine, DefaultImageExtensions),
            ExcludeDirectoriesText = string.Empty,
            ExcludeFileNamesText = string.Empty,
            ShowAdvancedOptions = false,
        };
    }

    private static string GetDefaultLogDirectory()
    {
        return Path.GetFullPath(InstallationPaths.GetLogDirectory());
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
}
