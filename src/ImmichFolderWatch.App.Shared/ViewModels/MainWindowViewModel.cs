using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using ImmichFolderWatch.App.Shared.Models;
using ImmichFolderWatch.App.Shared.Resources;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Installation;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.App.Shared.ViewModels;

public sealed class MainWindowViewModel : BindableBase
{
    private static readonly string[] DefaultImageExtensions =
    {
        ".3fr",
        ".3gp",
        ".3gpp",
        ".ari",
        ".arw",
        ".avi",
        ".avif",
        ".bmp",
        ".cap",
        ".cin",
        ".cr2",
        ".cr3",
        ".crw",
        ".dcr",
        ".dng",
        ".erf",
        ".fff",
        ".flv",
        ".gif",
        ".heic",
        ".heif",
        ".hif",
        ".iiq",
        ".insp",
        ".insv",
        ".jp2",
        ".jpe",
        ".jpeg",
        ".jpg",
        ".jxl",
        ".k25",
        ".kdc",
        ".m2t",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpe",
        ".mpeg",
        ".mpg",
        ".mrw",
        ".mts",
        ".nef",
        ".nrw",
        ".orf",
        ".ori",
        ".pef",
        ".png",
        ".psd",
        ".raf",
        ".raw",
        ".rw2",
        ".rwl",
        ".sr2",
        ".srf",
        ".srw",
        ".svg",
        ".tif",
        ".tiff",
        ".vob",
        ".webm",
        ".webp",
        ".wmv",
        ".x3f",
    };

    private readonly SyncStatusProvider _syncStatusProvider;
    private readonly IAutoStartManager _autostartManager;
    private readonly LocalizationService _localizationService;
    private readonly IUiDispatcher _uiDispatcher;
    private readonly IPlatformLoggingCapabilities _loggingCapabilities;
    private bool _suppressAutostartWrite;
    private bool _suppressLanguageWrite;

    private string _immichServerApiUrl = string.Empty;
    private string _immichApiKey = string.Empty;
    private string _batchIntervalSeconds = "5";
    private string _maxBatchSize = "25";
    private string _fileReadyTimeoutSeconds = "30";
    private string _retryMaxAttempts = "5";
    private string _retryBaseDelayMilliseconds = "500";
    private string _loggingLevel = "Information";
    private string _loggingTarget = LogTargets.EventLog;
    private string _logDirectory = GetDefaultLogDirectory();
    private string _statusHeadline = string.Empty;
    private string _statusDetails = string.Empty;
    private string _trayStatusMessage = string.Empty;
    private string _syncStatusBadgeText = string.Empty;
    private StatusTone _syncStatusBadgeTone = StatusTone.Neutral;
    private string _serverConnectionText = string.Empty;
    private StatusTone _serverConnectionTone = StatusTone.Neutral;
    private string _serverConnectionDetail = string.Empty;
    private string _lastSyncText = string.Empty;
    private string _currentUploadText = string.Empty;
    private string _pendingCountText = "0";
    private bool _autostartEnabled;
    private string _productVersionText = string.Empty;
    private string _operationMessage = string.Empty;
    private string _saveActionButtonText = string.Empty;
    private string _immichUrlStatusText = string.Empty;
    private StatusTone _immichUrlStatusTone = StatusTone.Neutral;
    private string _immichApiKeyStatusText = string.Empty;
    private StatusTone _immichApiKeyStatusTone = StatusTone.Neutral;
    private string _immichPermissionsStatusText = string.Empty;
    private StatusTone _immichPermissionsStatusTone = StatusTone.Neutral;
    private bool _revealImmichApiKey;
    private bool _shouldMaskImmichApiKey;
    private bool _showPlainImmichApiKeyInput = true;
    private bool _showImmichApiKeyRevealButton;
    private bool _isImmichApiKeyPlaceholder;
    private string _immichApiKeyRevealToolTip = string.Empty;
    private LanguageOption _selectedLanguage;

    public MainWindowViewModel(
        SyncStatusProvider syncStatusProvider,
        IAutoStartManager autostartManager,
        LocalizationService localizationService,
        IUiDispatcher uiDispatcher,
        IPlatformLoggingCapabilities loggingCapabilities)
    {
        _syncStatusProvider = syncStatusProvider ?? throw new ArgumentNullException(nameof(syncStatusProvider));
        _autostartManager = autostartManager ?? throw new ArgumentNullException(nameof(autostartManager));
        _localizationService = localizationService ?? throw new ArgumentNullException(nameof(localizationService));
        _uiDispatcher = uiDispatcher ?? throw new ArgumentNullException(nameof(uiDispatcher));
        _loggingCapabilities = loggingCapabilities ?? throw new ArgumentNullException(nameof(loggingCapabilities));
        _loggingTarget = _loggingCapabilities.DefaultTarget;

        AvailableLanguages = BuildLanguageOptions();
        _selectedLanguage = FindLanguageOption(_localizationService.CurrentLanguage);
        _saveActionButtonText = Strings.App_SaveAndApply;
        _statusHeadline = Strings.App_StatusHeadline_Running;
        _immichApiKeyRevealToolTip = Strings.ApiKey_ShowToolTip;

        RefreshSyncModeOptions();
        RefreshLogTargetOptions();

        AddSource();
        RefreshImmichApiKeyPresentation(resetVisibleState: true);
        ResetImmichCheckStatus();

        _suppressAutostartWrite = true;
        AutostartEnabled = _autostartManager.IsEnabledAsync().GetAwaiter().GetResult();
        _suppressAutostartWrite = false;

        RefreshSyncStatusFromProvider();
        _syncStatusProvider.PropertyChanged += SyncStatusProvider_PropertyChanged;
        _localizationService.LanguageChanged += LocalizationService_LanguageChanged;
    }

    public ObservableCollection<WatchSourceItem> Sources { get; } = new();

    public ObservableCollection<ImmichPermissionStatusItem> ImmichPermissionStatuses { get; } = new();

    public ObservableCollection<SyncModeOption> AvailableSyncModes { get; } = new();

    public ObservableCollection<LogTargetOption> AvailableLogTargets { get; } = new();

    public IReadOnlyList<LanguageOption> AvailableLanguages { get; }

    public LanguageOption SelectedLanguage
    {
        get => _selectedLanguage;
        set
        {
            if (value is null || SelectedLanguage == value)
            {
                return;
            }

            var previous = _selectedLanguage;
            if (!SetProperty(ref _selectedLanguage, value))
            {
                return;
            }

            if (_suppressLanguageWrite)
            {
                return;
            }

            try
            {
                _localizationService.SetLanguage(value.Code);
            }
            catch (Exception)
            {
                _suppressLanguageWrite = true;
                try
                {
                    _selectedLanguage = previous;
                    RaisePropertyChanged(nameof(SelectedLanguage));
                }
                finally
                {
                    _suppressLanguageWrite = false;
                }
            }
        }
    }

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

    public string LoggingTarget
    {
        get => _loggingTarget;
        set
        {
            var coerced = _loggingCapabilities.CoerceToSupported(value);
            if (SetProperty(ref _loggingTarget, coerced))
            {
                RaisePropertyChanged(nameof(IsFileLogTarget));
            }
        }
    }

    public bool IsFileLogTarget => LogTargets.IsFile(_loggingTarget);

    public string LogDirectory
    {
        get => _logDirectory;
        set => SetProperty(ref _logDirectory, value);
    }

    /// <summary>
    /// Set by the Linux head when AvaloniaTrayHost can't actually show a
    /// tray icon (probe failure or async ServiceUnknown from the SNI
    /// backend). Empty when the tray works or when the platform never
    /// uses a tray (WPF). The MainWindow shows it as a banner so the
    /// user knows closing the window will exit the process.
    /// </summary>
    public string TrayStatusMessage
    {
        get => _trayStatusMessage;
        set => SetProperty(ref _trayStatusMessage, value);
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

    public void Load(AppConfig config, bool resetImmichCheckStatus = true)
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
        LoggingTarget = LogTargets.Normalize(config.Logging.Target);
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
                SyncMode = source.SyncMode,
            });
        }

        if (Sources.Count == 0)
        {
            AddSource();
        }

        // Avalonia 11.3.x's ComboBox + SelectedValueBinding inside an
        // ItemsControl-DataTemplate doesn't reliably pick up the initial
        // SelectedValue when the WatchSourceItem is constructed via the
        // object initializer above (PropertyChanged fires before the
        // ComboBox subscribes; the ComboBox's first read happens before
        // items materialize). Posting a delayed PropertyChanged refresh
        // forces the ComboBox to re-evaluate after layout — making the
        // SyncMode dropdown actually display the saved value instead of
        // sticking on UploadNew.
        var sourcesSnapshot = Sources.ToList();
        _uiDispatcher.Post(() =>
        {
            foreach (var source in sourcesSnapshot)
            {
                source.RaiseSyncModeChangedForBindingRefresh();
            }
        });

        RefreshImmichApiKeyPresentation(resetVisibleState: true);
        if (resetImmichCheckStatus)
        {
            ResetImmichCheckStatus();
        }
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
        var loggingTarget = LogTargets.Normalize(LoggingTarget);
        var logDirectory = LogDirectory.Trim();

        if (LogTargets.IsFile(loggingTarget))
        {
            if (string.IsNullOrWhiteSpace(logDirectory))
            {
                errorList.Add("logging.logDirectory is required when logging.target is 'file'.");
            }
            else if (!Path.IsPathFullyQualified(logDirectory))
            {
                errorList.Add("logging.logDirectory must be an absolute path.");
            }
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
                    SyncMode = WatchSourceSyncModes.Normalize(source.SyncMode),
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
                Target = loggingTarget,
                LogDirectory = string.IsNullOrWhiteSpace(logDirectory) ? GetDefaultLogDirectory() : logDirectory,
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
                    SyncMode = WatchSourceSyncModes.Normalize(source.SyncMode),
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

        var checkingMessage = $"{Strings.Check_Checking}...";
        RefreshPermissionStatuses(CreatePermissionItems(
            new[]
            {
                new ImmichPermissionCheckResult { PermissionName = "asset.upload", State = CheckState.Checking, Message = checkingMessage, BlocksConfigVerification = true },
                new ImmichPermissionCheckResult { PermissionName = "album.read", State = CheckState.Checking, Message = checkingMessage },
                new ImmichPermissionCheckResult { PermissionName = "album.create", State = CheckState.Checking, Message = checkingMessage },
                new ImmichPermissionCheckResult { PermissionName = "albumAsset.create", State = CheckState.Checking, Message = checkingMessage },
                new ImmichPermissionCheckResult { PermissionName = "asset.download", State = CheckState.Checking, Message = checkingMessage },
                new ImmichPermissionCheckResult { PermissionName = "asset.read", State = CheckState.Checking, Message = checkingMessage },
                new ImmichPermissionCheckResult { PermissionName = "asset.delete", State = CheckState.Checking, Message = checkingMessage },
                new ImmichPermissionCheckResult { PermissionName = "albumAsset.delete", State = CheckState.Checking, Message = checkingMessage },
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
            AutostartEnabled = _autostartManager.IsEnabledAsync().GetAwaiter().GetResult();
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
                _autostartManager.EnableAsync().GetAwaiter().GetResult();
            }
            else
            {
                _autostartManager.DisableAsync().GetAwaiter().GetResult();
            }
        }
        catch (Exception ex)
        {
            OperationMessage = string.Format(_localizationService.CurrentCulture, Strings.Op_AutostartFailedFormat, ex.Message);
            _suppressAutostartWrite = true;
            try
            {
                AutostartEnabled = _autostartManager.IsEnabledAsync().GetAwaiter().GetResult();
            }
            finally
            {
                _suppressAutostartWrite = false;
            }
        }
    }

    private void SyncStatusProvider_PropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (_uiDispatcher.IsOnUiThread)
        {
            RefreshSyncStatusFromProvider();
        }
        else
        {
            _uiDispatcher.Post(RefreshSyncStatusFromProvider);
        }
    }

    private void LocalizationService_LanguageChanged(object? sender, EventArgs e)
    {
        if (_uiDispatcher.IsOnUiThread)
        {
            ApplyLocalizedStrings();
        }
        else
        {
            _uiDispatcher.Post(ApplyLocalizedStrings);
        }
    }

    private void ApplyLocalizedStrings()
    {
        StatusHeadline = Strings.App_StatusHeadline_Running;
        SaveActionButtonText = Strings.App_SaveAndApply;
        ImmichApiKeyRevealToolTip = RevealImmichApiKey ? Strings.ApiKey_HideToolTip : Strings.ApiKey_ShowToolTip;

        RefreshSyncModeOptions();
        RefreshLogTargetOptions();

        _suppressLanguageWrite = true;
        try
        {
            var match = FindLanguageOption(_localizationService.CurrentLanguage);
            if (!ReferenceEquals(match, _selectedLanguage))
            {
                _selectedLanguage = match;
                RaisePropertyChanged(nameof(SelectedLanguage));
            }
        }
        finally
        {
            _suppressLanguageWrite = false;
        }

        RefreshSyncStatusFromProvider();
        RefreshPermissionStatusTexts();
    }

    private void RefreshSyncStatusFromProvider()
    {
        ServerConnectionText = _syncStatusProvider.ServerConnection switch
        {
            ServerConnectionState.Ok => Strings.Server_Ok,
            ServerConnectionState.Error => Strings.Server_Error,
            ServerConnectionState.Checking => Strings.Server_Checking,
            _ => Strings.Server_Unknown,
        };

        ServerConnectionTone = StatusToneMapper.FromServerConnection(_syncStatusProvider.ServerConnection);

        if (_syncStatusProvider.ServerConnection == ServerConnectionState.Error
            && !string.IsNullOrWhiteSpace(_syncStatusProvider.LastErrorMessage))
        {
            ServerConnectionDetail = _syncStatusProvider.LastErrorMessage!;
        }
        else if (_syncStatusProvider.LastServerCheckUtc.HasValue)
        {
            var check = _syncStatusProvider.LastServerCheckUtc.Value.ToLocalTime();
            ServerConnectionDetail = string.Format(_localizationService.CurrentCulture, Strings.Status_LastCheckedFormat, check.ToString("HH:mm:ss", _localizationService.CurrentCulture));
        }
        else
        {
            ServerConnectionDetail = string.Empty;
        }

        LastSyncText = _syncStatusProvider.LastSyncCompletedUtc.HasValue
            ? _syncStatusProvider.LastSyncCompletedUtc.Value.ToLocalTime()
                .ToString("dd.MM.yyyy HH:mm:ss", _localizationService.CurrentCulture)
            : Strings.Status_NoSyncYet;

        if (!string.IsNullOrWhiteSpace(_syncStatusProvider.CurrentlyUploadingFile))
        {
            var fileName = Path.GetFileName(_syncStatusProvider.CurrentlyUploadingFile);
            var prefixed = string.Format(_localizationService.CurrentCulture, Strings.Status_UploadingPrefix, fileName);
            if (_syncStatusProvider.CurrentBatchSize > 0)
            {
                CurrentUploadText = $"{prefixed} ({_syncStatusProvider.UploadedInCurrentBatch + 1}/{_syncStatusProvider.CurrentBatchSize})";
            }
            else
            {
                CurrentUploadText = prefixed;
            }
        }
        else if (!string.IsNullOrWhiteSpace(_syncStatusProvider.CurrentlyDownloadingFile))
        {
            var fileName = Path.GetFileName(_syncStatusProvider.CurrentlyDownloadingFile);
            var prefixed = string.Format(_localizationService.CurrentCulture, Strings.Status_DownloadingPrefix, fileName);
            if (_syncStatusProvider.CurrentPullSize > 0)
            {
                CurrentUploadText = $"{prefixed} ({_syncStatusProvider.DownloadedInCurrentPull + 1}/{_syncStatusProvider.CurrentPullSize})";
            }
            else
            {
                CurrentUploadText = prefixed;
            }
        }
        else if (_syncStatusProvider.CurrentBatchSize > 0)
        {
            CurrentUploadText = string.Format(_localizationService.CurrentCulture, Strings.Status_BatchProgressFormat, _syncStatusProvider.UploadedInCurrentBatch, _syncStatusProvider.CurrentBatchSize);
        }
        else if (_syncStatusProvider.CurrentPullSize > 0)
        {
            CurrentUploadText = string.Format(_localizationService.CurrentCulture, Strings.Status_PullProgressFormat, _syncStatusProvider.DownloadedInCurrentPull, _syncStatusProvider.CurrentPullSize);
        }
        else
        {
            CurrentUploadText = Strings.Status_NoCurrentUpload;
        }

        PendingCountText = _syncStatusProvider.PendingCount.ToString(_localizationService.CurrentCulture);

        if (_syncStatusProvider.ServerConnection == ServerConnectionState.Error)
        {
            SyncStatusBadgeText = Strings.Status_ServerOffline;
            SyncStatusBadgeTone = StatusTone.Error;
        }
        else if (!string.IsNullOrWhiteSpace(_syncStatusProvider.CurrentlyUploadingFile)
                 || _syncStatusProvider.CurrentBatchSize > 0
                 || !string.IsNullOrWhiteSpace(_syncStatusProvider.CurrentlyDownloadingFile)
                 || _syncStatusProvider.CurrentPullSize > 0)
        {
            SyncStatusBadgeText = Strings.Status_SyncRunning;
            SyncStatusBadgeTone = StatusTone.Info;
        }
        else if (_syncStatusProvider.PendingCount > 0)
        {
            SyncStatusBadgeText = Strings.Status_Queue;
            SyncStatusBadgeTone = StatusTone.Info;
        }
        else if (_syncStatusProvider.ServerConnection == ServerConnectionState.Ok)
        {
            SyncStatusBadgeText = Strings.Status_Ready;
            SyncStatusBadgeTone = StatusTone.Success;
        }
        else
        {
            SyncStatusBadgeText = Strings.Status_Ready;
            SyncStatusBadgeTone = StatusTone.Neutral;
        }
    }

    private void RefreshPermissionStatusTexts()
    {
        SetImmichUrlStatus(CheckStateFromTone(ImmichUrlStatusTone));
        SetImmichApiKeyStatus(CheckStateFromTone(ImmichApiKeyStatusTone));
        SetImmichPermissionsStatus(CheckStateFromTone(ImmichPermissionsStatusTone));

        for (var i = 0; i < ImmichPermissionStatuses.Count; i++)
        {
            var existing = ImmichPermissionStatuses[i];
            ImmichPermissionStatuses[i] = new ImmichPermissionStatusItem
            {
                DisplayName = GetPermissionDisplayName(existing.PermissionName),
                PermissionName = existing.PermissionName,
                StatusText = existing.StatusText,
                StatusTone = existing.StatusTone,
                Message = existing.Message,
            };
        }
    }

    private static CheckState CheckStateFromTone(StatusTone tone)
    {
        return tone switch
        {
            StatusTone.Success => CheckState.Passed,
            StatusTone.Warning => CheckState.Warning,
            StatusTone.Error => CheckState.Failed,
            StatusTone.Info => CheckState.Checking,
            _ => CheckState.NotChecked,
        };
    }

    private void ResetImmichCheckStatus()
    {
        SetImmichUrlStatus(CheckState.NotChecked);
        SetImmichApiKeyStatus(CheckState.NotChecked);
        SetImmichPermissionsStatus(CheckState.NotChecked);

        RefreshPermissionStatuses(CreatePermissionItems(
            new[]
            {
                new ImmichPermissionCheckResult { PermissionName = "asset.upload", State = CheckState.NotChecked, Message = Strings.Check_NotCheckedYet, BlocksConfigVerification = true },
                new ImmichPermissionCheckResult { PermissionName = "album.read", State = CheckState.NotChecked, Message = Strings.Check_NotCheckedYet },
                new ImmichPermissionCheckResult { PermissionName = "album.create", State = CheckState.NotChecked, Message = Strings.Check_NotCheckedYet },
                new ImmichPermissionCheckResult { PermissionName = "albumAsset.create", State = CheckState.NotChecked, Message = Strings.Check_NotCheckedYet },
                new ImmichPermissionCheckResult { PermissionName = "asset.download", State = CheckState.NotChecked, Message = Strings.Check_NotCheckedYet },
                new ImmichPermissionCheckResult { PermissionName = "asset.read", State = CheckState.NotChecked, Message = Strings.Check_NotCheckedYet },
                new ImmichPermissionCheckResult { PermissionName = "asset.delete", State = CheckState.NotChecked, Message = Strings.Check_NotCheckedYet },
                new ImmichPermissionCheckResult { PermissionName = "albumAsset.delete", State = CheckState.NotChecked, Message = Strings.Check_NotCheckedYet },
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
            DisplayName = GetPermissionDisplayName(result.PermissionName),
            PermissionName = result.PermissionName,
            StatusText = GetCheckStateText(result.State),
            StatusTone = StatusToneMapper.FromCheckState(result.State),
            Message = result.Message,
        });
    }

    private static string GetPermissionDisplayName(string permissionName)
    {
        return permissionName switch
        {
            "asset.upload" => Strings.Permission_AssetUpload,
            "album.read" => Strings.Permission_AlbumRead,
            "album.create" => Strings.Permission_AlbumCreate,
            "albumAsset.create" => Strings.Permission_AddAssetToAlbum,
            "asset.download" => Strings.Permission_AssetDownload,
            "asset.read" => Strings.Permission_AssetRead,
            "asset.delete" => Strings.Permission_AssetDelete,
            "albumAsset.delete" => Strings.Permission_RemoveAssetFromAlbum,
            _ => permissionName,
        };
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
            SyncMode = WatchSourceSyncModes.UploadNew,
        };
    }

    private void RefreshSyncModeOptions()
    {
        var newOptions = new[]
        {
            new SyncModeOption(WatchSourceSyncModes.UploadNew, Strings.SyncMode_UploadNew, Strings.SyncMode_UploadNew_Description),
            new SyncModeOption(WatchSourceSyncModes.UploadAll, Strings.SyncMode_UploadAll, Strings.SyncMode_UploadAll_Description),
            new SyncModeOption(WatchSourceSyncModes.Sync, Strings.SyncMode_Sync, Strings.SyncMode_Sync_Description),
        };

        AvailableSyncModes.Clear();
        foreach (var option in newOptions)
        {
            AvailableSyncModes.Add(option);
        }
    }

    private void RefreshLogTargetOptions()
    {
        AvailableLogTargets.Clear();
        foreach (var target in _loggingCapabilities.SupportedTargets)
        {
            AvailableLogTargets.Add(new LogTargetOption(target, GetLogTargetDisplayName(target)));
        }
    }

    private static string GetLogTargetDisplayName(string target) => target switch
    {
        LogTargets.EventLog => Strings.UI_LogTargetEventLog,
        LogTargets.File => Strings.UI_LogTargetFile,
        LogTargets.Journald => Strings.UI_LogTargetJournald,
        _ => target,
    };

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
        ImmichApiKeyRevealToolTip = revealPassword ? Strings.ApiKey_HideToolTip : Strings.ApiKey_ShowToolTip;
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
            CheckState.Passed => Strings.Check_Ok,
            CheckState.Warning => Strings.Check_Warning,
            CheckState.Failed => Strings.Check_Failed,
            CheckState.Checking => Strings.Check_Checking,
            _ => Strings.Check_NotChecked,
        };
    }

    private static IReadOnlyList<LanguageOption> BuildLanguageOptions()
    {
        return new LanguageOption[]
        {
            new(LocalizationService.LanguageAuto, Strings.Language_Auto),
            new(LocalizationService.LanguageEnglish, Strings.Language_English),
            new(LocalizationService.LanguageGerman, Strings.Language_German),
        };
    }

    private LanguageOption FindLanguageOption(string code)
    {
        var normalized = LocalizationService.NormalizeCode(code);
        foreach (var option in AvailableLanguages)
        {
            if (string.Equals(option.Code, normalized, StringComparison.OrdinalIgnoreCase))
            {
                return option;
            }
        }

        return AvailableLanguages[0];
    }
}
