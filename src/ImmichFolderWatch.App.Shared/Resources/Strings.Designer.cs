#nullable enable
using System.Globalization;
using System.Resources;

namespace ImmichFolderWatch.App.Shared.Resources;

public static class Strings
{
    private static readonly ResourceManager Manager =
        new("ImmichFolderWatch.App.Shared.Resources.Strings", typeof(Strings).Assembly);

    public static CultureInfo? Culture { get; set; }

    public static ResourceManager ResourceManager => Manager;

    private static string Get(string key)
    {
        return Manager.GetString(key, Culture) ?? key;
    }

    public static string App_StatusHeadline_Running => Get(nameof(App_StatusHeadline_Running));
    public static string App_SaveAndApply => Get(nameof(App_SaveAndApply));

    public static string Status_Ready => Get(nameof(Status_Ready));
    public static string Status_ServerOffline => Get(nameof(Status_ServerOffline));
    public static string Status_SyncRunning => Get(nameof(Status_SyncRunning));
    public static string Status_Queue => Get(nameof(Status_Queue));
    public static string Status_NoSyncYet => Get(nameof(Status_NoSyncYet));
    public static string Status_NoCurrentUpload => Get(nameof(Status_NoCurrentUpload));
    public static string Status_LastCheckedFormat => Get(nameof(Status_LastCheckedFormat));
    public static string Status_BatchProgressFormat => Get(nameof(Status_BatchProgressFormat));
    public static string Status_UploadingPrefix => Get(nameof(Status_UploadingPrefix));
    public static string Status_DownloadingPrefix => Get(nameof(Status_DownloadingPrefix));
    public static string Status_PullProgressFormat => Get(nameof(Status_PullProgressFormat));

    public static string Server_Unknown => Get(nameof(Server_Unknown));
    public static string Server_Error => Get(nameof(Server_Error));
    public static string Server_Checking => Get(nameof(Server_Checking));
    public static string Server_Ok => Get(nameof(Server_Ok));

    public static string Tooltip_LastSync => Get(nameof(Tooltip_LastSync));
    public static string Tooltip_Queue => Get(nameof(Tooltip_Queue));

    public static string Tray_Open => Get(nameof(Tray_Open));
    public static string Tray_Restart => Get(nameof(Tray_Restart));
    public static string Tray_Quit => Get(nameof(Tray_Quit));

    public static string UI_Status => Get(nameof(UI_Status));
    public static string UI_ServerConnection => Get(nameof(UI_ServerConnection));
    public static string UI_LastSync => Get(nameof(UI_LastSync));
    public static string UI_CurrentSync => Get(nameof(UI_CurrentSync));
    public static string UI_PendingFiles => Get(nameof(UI_PendingFiles));
    public static string UI_Autostart => Get(nameof(UI_Autostart));
    public static string UI_StartOnLogin => Get(nameof(UI_StartOnLogin));
    public static string UI_AutostartDescription => Get(nameof(UI_AutostartDescription));
    public static string UI_Immich => Get(nameof(UI_Immich));
    public static string UI_ServerApiUrl => Get(nameof(UI_ServerApiUrl));
    public static string UI_ApiKey => Get(nameof(UI_ApiKey));
    public static string UI_Permissions => Get(nameof(UI_Permissions));
    public static string UI_PermissionsDescription => Get(nameof(UI_PermissionsDescription));
    public static string UI_VerifyImmichAccess => Get(nameof(UI_VerifyImmichAccess));
    public static string UI_WatchSources => Get(nameof(UI_WatchSources));
    public static string UI_AddSource => Get(nameof(UI_AddSource));
    public static string UI_WatchSource => Get(nameof(UI_WatchSource));
    public static string UI_Remove => Get(nameof(UI_Remove));
    public static string UI_FolderPath => Get(nameof(UI_FolderPath));
    public static string UI_ImmichAlbumName => Get(nameof(UI_ImmichAlbumName));
    public static string UI_AlbumNameWatermark => Get(nameof(UI_AlbumNameWatermark));
    public static string UI_AdvancedWatchOptions => Get(nameof(UI_AdvancedWatchOptions));
    public static string UI_IncludeSubdirectories => Get(nameof(UI_IncludeSubdirectories));
    public static string UI_Extensions => Get(nameof(UI_Extensions));
    public static string UI_ExcludedDirectories => Get(nameof(UI_ExcludedDirectories));
    public static string UI_ExcludedFileNames => Get(nameof(UI_ExcludedFileNames));
    public static string UI_WatchBehavior => Get(nameof(UI_WatchBehavior));
    public static string UI_BatchIntervalSeconds => Get(nameof(UI_BatchIntervalSeconds));
    public static string UI_MaxBatchSize => Get(nameof(UI_MaxBatchSize));
    public static string UI_FileReadyTimeoutSeconds => Get(nameof(UI_FileReadyTimeoutSeconds));
    public static string UI_RetryMaxAttempts => Get(nameof(UI_RetryMaxAttempts));
    public static string UI_LoggingAndRetry => Get(nameof(UI_LoggingAndRetry));
    public static string UI_RetryBaseDelayMs => Get(nameof(UI_RetryBaseDelayMs));
    public static string UI_LogLevel => Get(nameof(UI_LogLevel));
    public static string UI_LogTarget => Get(nameof(UI_LogTarget));
    public static string UI_LogTargetEventLog => Get(nameof(UI_LogTargetEventLog));
    public static string UI_LogTargetFile => Get(nameof(UI_LogTargetFile));
    public static string UI_LogDirectory => Get(nameof(UI_LogDirectory));
    public static string UI_UseDefault => Get(nameof(UI_UseDefault));
    public static string UI_LogDirectoryHint => Get(nameof(UI_LogDirectoryHint));
    public static string UI_OpenLogs => Get(nameof(UI_OpenLogs));
    public static string UI_Language => Get(nameof(UI_Language));
    public static string UI_Appearance => Get(nameof(UI_Appearance));
    public static string UI_SyncMode => Get(nameof(UI_SyncMode));

    public static string SyncMode_UploadNew => Get(nameof(SyncMode_UploadNew));
    public static string SyncMode_UploadNew_Description => Get(nameof(SyncMode_UploadNew_Description));
    public static string SyncMode_UploadAll => Get(nameof(SyncMode_UploadAll));
    public static string SyncMode_UploadAll_Description => Get(nameof(SyncMode_UploadAll_Description));
    public static string SyncMode_Sync => Get(nameof(SyncMode_Sync));
    public static string SyncMode_Sync_Description => Get(nameof(SyncMode_Sync_Description));

    public static string Permission_AssetUpload => Get(nameof(Permission_AssetUpload));
    public static string Permission_AlbumRead => Get(nameof(Permission_AlbumRead));
    public static string Permission_AlbumCreate => Get(nameof(Permission_AlbumCreate));
    public static string Permission_AddAssetToAlbum => Get(nameof(Permission_AddAssetToAlbum));
    public static string Permission_AssetDownload => Get(nameof(Permission_AssetDownload));
    public static string Permission_AssetRead => Get(nameof(Permission_AssetRead));
    public static string Permission_AssetDelete => Get(nameof(Permission_AssetDelete));
    public static string Permission_RemoveAssetFromAlbum => Get(nameof(Permission_RemoveAssetFromAlbum));

    public static string Check_Ok => Get(nameof(Check_Ok));
    public static string Check_Warning => Get(nameof(Check_Warning));
    public static string Check_Failed => Get(nameof(Check_Failed));
    public static string Check_Checking => Get(nameof(Check_Checking));
    public static string Check_NotChecked => Get(nameof(Check_NotChecked));
    public static string Check_NotCheckedYet => Get(nameof(Check_NotCheckedYet));

    public static string ApiKey_ShowToolTip => Get(nameof(ApiKey_ShowToolTip));
    public static string ApiKey_HideToolTip => Get(nameof(ApiKey_HideToolTip));

    public static string Op_ConfigLoadFailedFormat => Get(nameof(Op_ConfigLoadFailedFormat));
    public static string Op_CheckingImmich => Get(nameof(Op_CheckingImmich));
    public static string Op_ImmichCheckFailedFormat => Get(nameof(Op_ImmichCheckFailedFormat));
    public static string Op_ImmichCheckOk => Get(nameof(Op_ImmichCheckOk));
    public static string Op_ImmichCheckDone => Get(nameof(Op_ImmichCheckDone));
    public static string Op_NoLogDir => Get(nameof(Op_NoLogDir));
    public static string Op_LogDirMissingFormat => Get(nameof(Op_LogDirMissingFormat));
    public static string Op_LogDirReset => Get(nameof(Op_LogDirReset));
    public static string Op_EventLogSourceMissing => Get(nameof(Op_EventLogSourceMissing));
    public static string Op_EventLogSourceMisalignedFormat => Get(nameof(Op_EventLogSourceMisalignedFormat));
    public static string Op_EventViewerLaunchFailedFormat => Get(nameof(Op_EventViewerLaunchFailedFormat));
    public static string Op_CheckingConfig => Get(nameof(Op_CheckingConfig));
    public static string Op_SavingRestarting => Get(nameof(Op_SavingRestarting));
    public static string Op_SavedApplied => Get(nameof(Op_SavedApplied));
    public static string Op_SaveFailedFormat => Get(nameof(Op_SaveFailedFormat));
    public static string Op_AutostartFailedFormat => Get(nameof(Op_AutostartFailedFormat));

    public static string Language_Auto => Get(nameof(Language_Auto));
    public static string Language_English => Get(nameof(Language_English));
    public static string Language_German => Get(nameof(Language_German));
}
