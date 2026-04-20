using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class EnsureAlbumResult
{
    private EnsureAlbumResult(bool isSuccess, string? albumId, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        AlbumId = albumId;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public string? AlbumId { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static EnsureAlbumResult Success(string albumId)
    {
        return new EnsureAlbumResult(true, albumId, null, null);
    }

    public static EnsureAlbumResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new EnsureAlbumResult(false, null, statusCode, errorMessage);
    }
}
