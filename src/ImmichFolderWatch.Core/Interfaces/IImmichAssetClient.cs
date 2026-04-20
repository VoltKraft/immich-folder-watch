using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IImmichAssetClient
{
    Task PingAsync(CancellationToken cancellationToken);

    Task<UploadAssetResult> UploadAssetAsync(UploadAssetRequest request, CancellationToken cancellationToken);

    Task<AlbumAssetsResult> GetAlbumAssetsAsync(string albumName, CancellationToken cancellationToken);

    Task<DownloadAssetResult> DownloadAssetAsync(string assetId, string destinationPath, CancellationToken cancellationToken);
}
