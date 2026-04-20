using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class AlbumListResult
{
    private AlbumListResult(bool isSuccess, IReadOnlyList<AlbumInfo> albums, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        Albums = albums;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public IReadOnlyList<AlbumInfo> Albums { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static AlbumListResult Success(IReadOnlyList<AlbumInfo> albums)
    {
        return new AlbumListResult(true, albums, null, null);
    }

    public static AlbumListResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new AlbumListResult(false, Array.Empty<AlbumInfo>(), statusCode, errorMessage);
    }
}
