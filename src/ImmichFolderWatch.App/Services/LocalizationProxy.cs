using System.ComponentModel;
using System.Windows;
using ImmichFolderWatch.App.Resources;

namespace ImmichFolderWatch.App.Services;

public sealed class LocalizationProxy : INotifyPropertyChanged
{
    public LocalizationProxy()
        : this(LocalizationService.Instance)
    {
    }

    public LocalizationProxy(LocalizationService localizationService)
    {
        localizationService.LanguageChanged += OnLanguageChanged;
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public string App_StatusHeadline_Running => Strings.App_StatusHeadline_Running;
    public string App_SaveAndApply => Strings.App_SaveAndApply;

    public string Status_Ready => Strings.Status_Ready;
    public string Status_ServerOffline => Strings.Status_ServerOffline;
    public string Status_SyncRunning => Strings.Status_SyncRunning;
    public string Status_Queue => Strings.Status_Queue;
    public string Status_NoSyncYet => Strings.Status_NoSyncYet;
    public string Status_NoCurrentUpload => Strings.Status_NoCurrentUpload;
    public string Status_LastCheckedFormat => Strings.Status_LastCheckedFormat;
    public string Status_BatchProgressFormat => Strings.Status_BatchProgressFormat;

    public string Server_Unknown => Strings.Server_Unknown;
    public string Server_Error => Strings.Server_Error;
    public string Server_Checking => Strings.Server_Checking;
    public string Server_Ok => Strings.Server_Ok;

    public string Tooltip_LastSync => Strings.Tooltip_LastSync;
    public string Tooltip_Queue => Strings.Tooltip_Queue;

    public string Tray_Open => Strings.Tray_Open;
    public string Tray_Restart => Strings.Tray_Restart;
    public string Tray_Quit => Strings.Tray_Quit;

    public string UI_Status => Strings.UI_Status;
    public string UI_ServerConnection => Strings.UI_ServerConnection;
    public string UI_LastSync => Strings.UI_LastSync;
    public string UI_CurrentSync => Strings.UI_CurrentSync;
    public string UI_PendingFiles => Strings.UI_PendingFiles;
    public string UI_Autostart => Strings.UI_Autostart;
    public string UI_StartOnLogin => Strings.UI_StartOnLogin;
    public string UI_AutostartDescription => Strings.UI_AutostartDescription;
    public string UI_Immich => Strings.UI_Immich;
    public string UI_ServerApiUrl => Strings.UI_ServerApiUrl;
    public string UI_ApiKey => Strings.UI_ApiKey;
    public string UI_Permissions => Strings.UI_Permissions;
    public string UI_PermissionsDescription => Strings.UI_PermissionsDescription;
    public string UI_VerifyImmichAccess => Strings.UI_VerifyImmichAccess;
    public string UI_WatchSources => Strings.UI_WatchSources;
    public string UI_AddSource => Strings.UI_AddSource;
    public string UI_WatchSource => Strings.UI_WatchSource;
    public string UI_Remove => Strings.UI_Remove;
    public string UI_FolderPath => Strings.UI_FolderPath;
    public string UI_ImmichAlbumName => Strings.UI_ImmichAlbumName;
    public string UI_AlbumNameWatermark => Strings.UI_AlbumNameWatermark;
    public string UI_AdvancedWatchOptions => Strings.UI_AdvancedWatchOptions;
    public string UI_IncludeSubdirectories => Strings.UI_IncludeSubdirectories;
    public string UI_Extensions => Strings.UI_Extensions;
    public string UI_ExcludedDirectories => Strings.UI_ExcludedDirectories;
    public string UI_ExcludedFileNames => Strings.UI_ExcludedFileNames;
    public string UI_WatchBehavior => Strings.UI_WatchBehavior;
    public string UI_BatchIntervalSeconds => Strings.UI_BatchIntervalSeconds;
    public string UI_MaxBatchSize => Strings.UI_MaxBatchSize;
    public string UI_FileReadyTimeoutSeconds => Strings.UI_FileReadyTimeoutSeconds;
    public string UI_RetryMaxAttempts => Strings.UI_RetryMaxAttempts;
    public string UI_LoggingAndRetry => Strings.UI_LoggingAndRetry;
    public string UI_RetryBaseDelayMs => Strings.UI_RetryBaseDelayMs;
    public string UI_LogLevel => Strings.UI_LogLevel;
    public string UI_LogDirectory => Strings.UI_LogDirectory;
    public string UI_UseDefault => Strings.UI_UseDefault;
    public string UI_LogDirectoryHint => Strings.UI_LogDirectoryHint;
    public string UI_OpenLogs => Strings.UI_OpenLogs;
    public string UI_Language => Strings.UI_Language;
    public string UI_Appearance => Strings.UI_Appearance;

    public string Permission_AssetUpload => Strings.Permission_AssetUpload;
    public string Permission_AlbumRead => Strings.Permission_AlbumRead;
    public string Permission_AlbumCreate => Strings.Permission_AlbumCreate;
    public string Permission_AddAssetToAlbum => Strings.Permission_AddAssetToAlbum;

    public string Check_Ok => Strings.Check_Ok;
    public string Check_Warning => Strings.Check_Warning;
    public string Check_Failed => Strings.Check_Failed;
    public string Check_Checking => Strings.Check_Checking;
    public string Check_NotChecked => Strings.Check_NotChecked;
    public string Check_NotCheckedYet => Strings.Check_NotCheckedYet;

    public string ApiKey_ShowToolTip => Strings.ApiKey_ShowToolTip;
    public string ApiKey_HideToolTip => Strings.ApiKey_HideToolTip;

    public string Op_ConfigLoadFailedFormat => Strings.Op_ConfigLoadFailedFormat;
    public string Op_CheckingImmich => Strings.Op_CheckingImmich;
    public string Op_ImmichCheckFailedFormat => Strings.Op_ImmichCheckFailedFormat;
    public string Op_ImmichCheckOk => Strings.Op_ImmichCheckOk;
    public string Op_ImmichCheckDone => Strings.Op_ImmichCheckDone;
    public string Op_NoLogDir => Strings.Op_NoLogDir;
    public string Op_LogDirMissingFormat => Strings.Op_LogDirMissingFormat;
    public string Op_LogDirReset => Strings.Op_LogDirReset;
    public string Op_CheckingConfig => Strings.Op_CheckingConfig;
    public string Op_SavingRestarting => Strings.Op_SavingRestarting;
    public string Op_SavedApplied => Strings.Op_SavedApplied;
    public string Op_SaveFailedFormat => Strings.Op_SaveFailedFormat;
    public string Op_AutostartFailedFormat => Strings.Op_AutostartFailedFormat;

    public string Language_Auto => Strings.Language_Auto;
    public string Language_English => Strings.Language_English;
    public string Language_German => Strings.Language_German;

    private void OnLanguageChanged(object? sender, EventArgs e)
    {
        var handler = PropertyChanged;
        if (handler is null)
        {
            return;
        }

        void Raise()
        {
            handler.Invoke(this, new PropertyChangedEventArgs(string.Empty));
        }

        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher is not null && !dispatcher.CheckAccess())
        {
            dispatcher.Invoke(Raise);
        }
        else
        {
            Raise();
        }
    }
}
