using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IImmichAssetClient
{
    Task PingAsync(CancellationToken cancellationToken);

    Task<UploadAssetResult> UploadAssetAsync(UploadAssetRequest request, CancellationToken cancellationToken);

    Task<AlbumAssetsResult> GetAlbumAssetsAsync(string albumName, CancellationToken cancellationToken);

    Task<DownloadAssetResult> DownloadAssetAsync(string assetId, string destinationPath, CancellationToken cancellationToken);

    Task<AlbumListResult> ListAlbumsAsync(CancellationToken cancellationToken);

    Task<UnassignedAssetsResult> GetUnassignedAssetsAsync(CancellationToken cancellationToken);

    Task<AlbumMembershipUpdateResult> AddAssetsToAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken);

    Task<AlbumMembershipUpdateResult> RemoveAssetsFromAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken);

    Task<TrashAssetsResult> TrashAssetsAsync(IReadOnlyList<string> assetIds, CancellationToken cancellationToken);

    Task<EnsureAlbumResult> EnsureAlbumAsync(string albumName, CancellationToken cancellationToken);

    Task<DeleteAlbumResult> DeleteAlbumAsync(string albumName, CancellationToken cancellationToken);

    Task<RenameAlbumResult> RenameAlbumAsync(string oldAlbumName, string newAlbumName, CancellationToken cancellationToken);
}
