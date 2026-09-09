using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.App.Shared.Services;

/// <summary>
/// Validates, saves, and applies configuration identically for the desktop hosts.
/// Each window must serialize its calls while an apply operation is in progress.
/// </summary>
public sealed class ConfigApplyService
{
    private readonly Func<AppConfig, string, CancellationToken, Task<ImmichAccessCheckResult>> _checkAccessAsync;

    /// <param name="checkAccessAsync">
    /// Optional access checker receiving the normalized draft, absolute config path, and cancellation
    /// token. Null uses the production Immich checker.
    /// </param>
    public ConfigApplyService(Func<AppConfig, string, CancellationToken, Task<ImmichAccessCheckResult>>? checkAccessAsync = null)
    {
        _checkAccessAsync = checkAccessAsync ?? new ConfigVerificationRunner().CheckImmichAccessAsync;
    }

    /// <summary>
    /// Normalizes paths relative to the config file, validates local settings, and checks Immich access.
    /// Validation failures return errors without writing or restarting. After successful validation,
    /// the normalized configuration is written with <see cref="AppConfigWriter"/> before awaiting
    /// <paramref name="restartAsync"/>. I/O, access-check, cancellation, and restart exceptions propagate;
    /// a restart failure leaves the saved configuration available for correction or another attempt.
    /// </summary>
    /// <param name="config">Configuration draft; normalization preserves the draft's original paths.</param>
    /// <param name="targetConfigPath">File to replace only after successful validation.</param>
    /// <param name="restartAsync">Host restart operation receiving the normalized, saved configuration.</param>
    /// <param name="accessChecked">Receives access-check results before saving; not called for local validation errors.</param>
    /// <param name="saving">Runs after successful validation and immediately before saving.</param>
    /// <param name="cancellationToken">Cancels access checking, saving, and the supplied host restart.</param>
    /// <returns>Validation errors, or success once saving and restarting have both completed.</returns>
    public async Task<VerificationResult> ApplyAsync(
        AppConfig config,
        string targetConfigPath,
        Func<AppConfig, CancellationToken, Task> restartAsync,
        Action<ImmichAccessCheckResult>? accessChecked = null,
        Action? saving = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentException.ThrowIfNullOrWhiteSpace(targetConfigPath);
        ArgumentNullException.ThrowIfNull(restartAsync);
        cancellationToken.ThrowIfCancellationRequested();

        var fullPath = Path.GetFullPath(targetConfigPath);
        var configDirectory = Path.GetDirectoryName(fullPath) ?? AppContext.BaseDirectory;
        var normalizedConfig = AppConfigLoader.NormalizeForRuntime(config, configDirectory);
        var validationErrors = AppConfigValidator.Validate(normalizedConfig);
        if (validationErrors.Count > 0)
        {
            return VerificationResult.Failed(validationErrors);
        }

        ImmichAccessCheckResult accessResult;
        try
        {
            accessResult = await _checkAccessAsync(normalizedConfig, fullPath, cancellationToken);
        }
        catch (Exception ex)
        {
            accessChecked?.Invoke(ConfigVerificationRunner.CreateUnexpectedFailureResult(ex, normalizedConfig));
            throw;
        }

        accessChecked?.Invoke(accessResult);
        var blockingErrors = accessResult.GetBlockingErrors();
        if (blockingErrors.Count > 0)
        {
            return VerificationResult.Failed(blockingErrors);
        }

        cancellationToken.ThrowIfCancellationRequested();
        saving?.Invoke();
        var yaml = new AppConfigWriter().Serialize(normalizedConfig);
        Directory.CreateDirectory(configDirectory);
        await File.WriteAllTextAsync(fullPath, yaml, cancellationToken);
        await restartAsync(normalizedConfig, cancellationToken);
        return VerificationResult.Passed();
    }
}
