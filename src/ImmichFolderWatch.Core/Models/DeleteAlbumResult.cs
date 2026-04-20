using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class DeleteAlbumResult
{
    private DeleteAlbumResult(bool isSuccess, bool albumMissing, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        AlbumMissing = albumMissing;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public bool AlbumMissing { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static DeleteAlbumResult Success()
    {
        return new DeleteAlbumResult(true, false, null, null);
    }

    public static DeleteAlbumResult Missing()
    {
        return new DeleteAlbumResult(true, true, null, null);
    }

    public static DeleteAlbumResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new DeleteAlbumResult(false, false, statusCode, errorMessage);
    }
}
