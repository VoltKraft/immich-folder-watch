using System.Net.Http;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Immich;

namespace ImmichFolderWatch.App.Services;

internal sealed class ConfigVerificationRunner
{
    public async Task<ImmichAccessCheckResult> CheckImmichAccessAsync(AppConfig config, string targetConfigPath, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentException.ThrowIfNullOrWhiteSpace(targetConfigPath);

        var normalizedConfig = NormalizeConfig(config, targetConfigPath);
        var requireAlbumPermissions = RequiresAlbumPermissions(normalizedConfig);
        var requireDownloadPermissions = RequiresDownloadPermissions(normalizedConfig);

        var urlError = AppConfigValidator.ValidateServerApiUrl(normalizedConfig.Immich.ServerApiUrl);
        var apiKeyError = AppConfigValidator.ValidateApiKey(normalizedConfig.Immich.ApiKey);
        if (!string.IsNullOrWhiteSpace(urlError) || !string.IsNullOrWhiteSpace(apiKeyError))
        {
            return CreateValidationFailureResult(urlError, apiKeyError, requireAlbumPermissions, requireDownloadPermissions);
        }

        using var httpClient = CreateHttpClient(normalizedConfig);
        var accessChecker = new ImmichAccessChecker(httpClient);
        return await accessChecker.CheckAsync(requireAlbumPermissions, requireDownloadPermissions, cancellationToken);
    }

    public async Task<VerificationResult> VerifyAsync(AppConfig config, string targetConfigPath, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentException.ThrowIfNullOrWhiteSpace(targetConfigPath);

        var accessResult = await CheckImmichAccessAsync(config, targetConfigPath, cancellationToken);
        return BuildVerificationResult(config, targetConfigPath, accessResult);
    }

    public VerificationResult BuildVerificationResult(AppConfig config, string targetConfigPath, ImmichAccessCheckResult accessResult)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentException.ThrowIfNullOrWhiteSpace(targetConfigPath);
        ArgumentNullException.ThrowIfNull(accessResult);

        var normalizedConfig = NormalizeConfig(config, targetConfigPath);
        var validationErrors = AppConfigValidator.Validate(normalizedConfig);
        if (validationErrors.Count > 0)
        {
            return VerificationResult.Failed(validationErrors);
        }

        var blockingErrors = accessResult.GetBlockingErrors();
        return blockingErrors.Count > 0
            ? VerificationResult.Failed(blockingErrors)
            : VerificationResult.Passed();
    }

    private static HttpClient CreateHttpClient(AppConfig normalizedConfig)
    {
        var httpClient = new HttpClient
        {
            BaseAddress = new Uri(AppConfigValidator.EnsureTrailingSlash(normalizedConfig.Immich.ServerApiUrl), UriKind.Absolute),
            Timeout = TimeSpan.FromMinutes(2),
        };

        httpClient.DefaultRequestHeaders.Add("x-api-key", normalizedConfig.Immich.ApiKey);
        httpClient.DefaultRequestHeaders.UserAgent.ParseAdd($"immich-folder-watch-gui/{ProductVersionProvider.GetProductVersion()}");
        return httpClient;
    }

    private static AppConfig NormalizeConfig(AppConfig config, string targetConfigPath)
    {
        var configDirectory = Path.GetDirectoryName(Path.GetFullPath(targetConfigPath)) ?? AppContext.BaseDirectory;
        return AppConfigLoader.NormalizeForRuntime(config, configDirectory);
    }

    private static bool RequiresAlbumPermissions(AppConfig config)
    {
        return config.Watch.Sources.Any(source => !string.IsNullOrWhiteSpace(source.AlbumName));
    }

    private static bool RequiresDownloadPermissions(AppConfig config)
    {
        return config.Watch.Sources.Any(source =>
            string.Equals(WatchSourceSyncModes.Normalize(source.SyncMode), WatchSourceSyncModes.Sync, StringComparison.Ordinal));
    }

    private static ImmichAccessCheckResult CreateValidationFailureResult(string? urlError, string? apiKeyError, bool requireAlbumPermissions, bool requireDownloadPermissions)
    {
        return new ImmichAccessCheckResult
        {
            UrlState = string.IsNullOrWhiteSpace(urlError) ? CheckState.NotChecked : CheckState.Failed,
            UrlMessage = string.IsNullOrWhiteSpace(urlError) ? "Not checked yet." : urlError,
            ApiKeyState = string.IsNullOrWhiteSpace(apiKeyError) ? CheckState.NotChecked : CheckState.Failed,
            ApiKeyMessage = string.IsNullOrWhiteSpace(apiKeyError) ? "Not checked yet." : apiKeyError,
            PermissionsState = CheckState.NotChecked,
            PermissionsMessage = "Not checked because the Immich inputs are not valid yet.",
            PermissionResults =
            [
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Asset Upload",
                    PermissionName = "asset.upload",
                    State = CheckState.NotChecked,
                    Message = "Not checked because the Immich inputs are not valid yet.",
                    BlocksConfigVerification = true,
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Album Read",
                    PermissionName = "album.read",
                    State = CheckState.NotChecked,
                    Message = "Not checked because the Immich inputs are not valid yet.",
                    BlocksConfigVerification = requireAlbumPermissions,
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Album Create",
                    PermissionName = "album.create",
                    State = CheckState.NotChecked,
                    Message = "Not checked because the Immich inputs are not valid yet.",
                    BlocksConfigVerification = requireAlbumPermissions,
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Add Asset To Album",
                    PermissionName = "albumAsset.create",
                    State = CheckState.NotChecked,
                    Message = "Not checked because the Immich inputs are not valid yet.",
                    BlocksConfigVerification = requireAlbumPermissions,
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Asset Download",
                    PermissionName = "asset.download",
                    State = CheckState.NotChecked,
                    Message = "Not checked because the Immich inputs are not valid yet.",
                    BlocksConfigVerification = requireDownloadPermissions,
                },
            ],
        };
    }
}
