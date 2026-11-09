using System.Net;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Immich;

public sealed partial class ImmichAssetClient
{
    public async Task<EnsureAlbumResult> CreateOwnedAlbumAsync(string albumName, CancellationToken cancellationToken)
    {
        var name = NormalizeAlbumName(albumName);
        if (string.IsNullOrWhiteSpace(name))
        {
            return EnsureAlbumResult.Failure(null, "Album name is required.");
        }

        var albums = await GetAlbumsAsync(cancellationToken);
        if (!albums.IsSuccess)
        {
            return EnsureAlbumResult.Failure(albums.StatusCode, albums.ErrorMessage);
        }

        if (FindExactAlbumMatches(albums.Albums, name).Count != 0)
        {
            return EnsureAlbumResult.Failure(HttpStatusCode.Conflict, "An existing album cannot be adopted for destructive folder operations.");
        }

        var result = await SendJsonAsync(HttpMethod.Post, ImmichApiRoutes.Albums, new { albumName = name }, cancellationToken);
        // Only the ID returned by this creation confers authority. Never recover an
        // uncertain POST by looking up a name: that could adopt someone else's album.
        if (!result.IsSuccessStatusCode || !TryExtractAlbum(result.Body, out var created)
            || !IsSafeAlbumId(created.Id)
            || !string.Equals(created.Name, name, StringComparison.Ordinal)
            || albums.Albums.Any(album => album.Id == created.Id))
        {
            return EnsureAlbumResult.Failure(result.StatusCode, "Album creation did not return a verifiable new album ID.");
        }

        return EnsureAlbumResult.Success(created.Id);
    }

    public async Task<DeleteAlbumResult> DeleteAlbumByIdAsync(string albumId, CancellationToken cancellationToken)
    {
        if (!IsSafeAlbumId(albumId)) throw new ArgumentException("Invalid album ID.", nameof(albumId));
        var result = await SendAsync(HttpMethod.Delete, ImmichApiRoutes.AlbumInfo(albumId), null, cancellationToken);
        if (result.StatusCode == HttpStatusCode.NotFound) return DeleteAlbumResult.Missing();
        return result.IsSuccessStatusCode
            ? DeleteAlbumResult.Success()
            : DeleteAlbumResult.Failure(result.StatusCode, "ID-bound album deletion failed.");
    }

    public async Task<RenameAlbumResult> RenameAlbumByIdAsync(string albumId, string newName, CancellationToken cancellationToken)
    {
        if (!IsSafeAlbumId(albumId)) throw new ArgumentException("Invalid album ID.", nameof(albumId));
        var name = NormalizeAlbumName(newName);
        if (string.IsNullOrWhiteSpace(name)) return RenameAlbumResult.Failure(null, "Album name is required.");
        var albums = await GetAlbumsAsync(cancellationToken);
        if (!albums.IsSuccess) return RenameAlbumResult.Failure(albums.StatusCode, albums.ErrorMessage);
        if (!albums.Albums.Any(album => album.Id == albumId)) return RenameAlbumResult.Missing();
        if (FindExactAlbumMatches(albums.Albums, name).Any(album => album.Id != albumId))
        {
            return RenameAlbumResult.Failure(HttpStatusCode.Conflict, "The destination album name is already in use.");
        }

        var result = await SendJsonAsync(HttpMethod.Patch, ImmichApiRoutes.AlbumInfo(albumId), new { albumName = name }, cancellationToken);
        if (result.StatusCode == HttpStatusCode.NotFound) return RenameAlbumResult.Missing();
        return result.IsSuccessStatusCode
            ? RenameAlbumResult.Success(albumId)
            : RenameAlbumResult.Failure(result.StatusCode, "ID-bound album rename failed.");
    }
    private static bool IsSafeAlbumId(string id) => !string.IsNullOrWhiteSpace(id)
        && id.All(c => char.IsAsciiLetterOrDigit(c) || c is '-' or '_');
}
