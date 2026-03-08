using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Services;

public sealed class ConfigVerificationService : IConfigVerificationService
{
    private readonly IImmichConnectivityVerifier _immichConnectivityVerifier;

    public ConfigVerificationService(IImmichConnectivityVerifier immichConnectivityVerifier)
    {
        _immichConnectivityVerifier = immichConnectivityVerifier;
    }

    public async Task<VerificationResult> VerifyAsync(AppConfig config, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(config);

        var validationErrors = AppConfigValidator.Validate(config);
        if (validationErrors.Count > 0)
        {
            return VerificationResult.Failed(validationErrors);
        }

        try
        {
            await _immichConnectivityVerifier.PingAsync(cancellationToken);
            return VerificationResult.Passed();
        }
        catch (Exception ex)
        {
            return VerificationResult.Failed(new[]
            {
                $"Immich connectivity check failed: {ex.Message}",
            });
        }
    }
}
