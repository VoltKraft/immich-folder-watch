using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IImmichAssetClient
{
    Task PingAsync(CancellationToken cancellationToken);

    Task<UploadAssetResult> UploadAssetAsync(UploadAssetRequest request, CancellationToken cancellationToken);
}
