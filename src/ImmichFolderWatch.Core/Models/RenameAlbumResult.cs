using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class RenameAlbumResult
{
    private RenameAlbumResult(bool isSuccess, bool albumMissing, string? albumId, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        AlbumMissing = albumMissing;
        AlbumId = albumId;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public bool AlbumMissing { get; }

    public string? AlbumId { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static RenameAlbumResult Success(string albumId)
    {
        return new RenameAlbumResult(true, false, albumId, null, null);
    }

    public static RenameAlbumResult Missing()
    {
        return new RenameAlbumResult(true, true, null, null, null);
    }

    public static RenameAlbumResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new RenameAlbumResult(false, false, null, statusCode, errorMessage);
    }
}
