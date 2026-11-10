using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IImmichAssetClient
{
    Task PingAsync(CancellationToken cancellationToken);

    Task<UploadAssetResult> UploadAssetAsync(UploadAssetRequest request, CancellationToken cancellationToken);

    Task<UploadAssetResult> UploadAssetAttemptAsync(
        UploadAssetRequest request,
        CancellationToken cancellationToken) => UploadAssetAsync(request, cancellationToken);

    Task<AlbumAssetsResult> GetAlbumAssetsAsync(string albumName, CancellationToken cancellationToken);

    Task<DownloadAssetResult> DownloadAssetAsync(string assetId, string destinationPath, CancellationToken cancellationToken);

    /// <summary>Writes remote bytes to an already authorized staging handle. The caller publishes and disposes the lease.</summary>
    Task<DownloadAssetResult> DownloadAssetAsync(string assetId, SecureDownloadLease destination, CancellationToken cancellationToken) =>
        Task.FromResult(DownloadAssetResult.Failure(null, "Handle-bound downloads are unavailable."));

    Task<AlbumListResult> ListAlbumsAsync(CancellationToken cancellationToken);

    Task<UnassignedAssetsResult> GetUnassignedAssetsAsync(CancellationToken cancellationToken);

    Task<AlbumMembershipUpdateResult> AddAssetsToAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken);

    Task<AlbumMembershipUpdateResult> RemoveAssetsFromAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken);

    Task<TrashAssetsResult> TrashAssetsAsync(IReadOnlyList<string> assetIds, CancellationToken cancellationToken);

    Task<EnsureAlbumResult> EnsureAlbumAsync(string albumName, CancellationToken cancellationToken);

    Task<DeleteAlbumResult> DeleteAlbumAsync(string albumName, CancellationToken cancellationToken);

    Task<RenameAlbumResult> RenameAlbumAsync(string oldAlbumName, string newAlbumName, CancellationToken cancellationToken);
    /// <summary>Creates a new album without adopting an existing same-name album.</summary>
    Task<EnsureAlbumResult> CreateOwnedAlbumAsync(string albumName, CancellationToken cancellationToken) =>
        Task.FromResult(EnsureAlbumResult.Failure(null, "Owned album creation is unavailable."));

    /// <summary>Deletes exactly the previously authorized album ID, without name lookup.</summary>
    Task<DeleteAlbumResult> DeleteAlbumByIdAsync(string albumId, CancellationToken cancellationToken) =>
        Task.FromResult(DeleteAlbumResult.Failure(null, "ID-bound album deletion is unavailable."));

    /// <summary>Renames exactly the previously authorized album ID, without a source-name lookup.</summary>
    Task<RenameAlbumResult> RenameAlbumByIdAsync(string albumId, string newName, CancellationToken cancellationToken) =>
        Task.FromResult(RenameAlbumResult.Failure(null, "ID-bound album rename is unavailable."));
}
