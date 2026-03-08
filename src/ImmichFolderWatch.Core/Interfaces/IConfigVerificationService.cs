using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IConfigVerificationService
{
    Task<VerificationResult> VerifyAsync(AppConfig config, CancellationToken cancellationToken);
}
