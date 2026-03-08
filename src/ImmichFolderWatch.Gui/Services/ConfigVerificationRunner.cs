using System.Reflection;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Gui.Services;

internal sealed class ConfigVerificationRunner
{
    public async Task<VerificationResult> VerifyAsync(AppConfig config, string targetConfigPath, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentException.ThrowIfNullOrWhiteSpace(targetConfigPath);

        var configDirectory = Path.GetDirectoryName(Path.GetFullPath(targetConfigPath)) ?? AppContext.BaseDirectory;
        var normalizedConfig = AppConfigLoader.NormalizeForRuntime(config, configDirectory);

        using var httpClient = new HttpClient
        {
            BaseAddress = new Uri(AppConfigValidator.EnsureTrailingSlash(normalizedConfig.Immich.ServerApiUrl), UriKind.Absolute),
            Timeout = TimeSpan.FromMinutes(2),
        };

        httpClient.DefaultRequestHeaders.Add("x-api-key", normalizedConfig.Immich.ApiKey);
        httpClient.DefaultRequestHeaders.UserAgent.ParseAdd($"immich-folder-watch-gui/{GetProductVersion()}");

        IImmichConnectivityVerifier connectivityVerifier = new ImmichAssetClient(
            httpClient,
            normalizedConfig.Retry,
            NullLogger<ImmichAssetClient>.Instance);

        var verificationService = new ConfigVerificationService(connectivityVerifier);
        return await verificationService.VerifyAsync(normalizedConfig, cancellationToken);
    }

    private static string GetProductVersion()
    {
        var informationalVersion = typeof(ConfigVerificationRunner)
            .Assembly
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
            ?.InformationalVersion;

        if (!string.IsNullOrWhiteSpace(informationalVersion))
        {
            var plusIndex = informationalVersion.IndexOf('+');
            return plusIndex >= 0
                ? informationalVersion[..plusIndex]
                : informationalVersion;
        }

        return "1.0.1";
    }
}
