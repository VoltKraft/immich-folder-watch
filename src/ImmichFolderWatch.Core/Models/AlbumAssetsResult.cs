using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class AlbumAssetsResult
{
    private AlbumAssetsResult(bool isSuccess, bool albumMissing, IReadOnlyList<AlbumAssetSummary> assets, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        AlbumMissing = albumMissing;
        Assets = assets;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public bool AlbumMissing { get; }

    public IReadOnlyList<AlbumAssetSummary> Assets { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static AlbumAssetsResult Success(IReadOnlyList<AlbumAssetSummary> assets)
    {
        return new AlbumAssetsResult(true, false, assets, null, null);
    }

    public static AlbumAssetsResult Missing()
    {
        return new AlbumAssetsResult(false, true, Array.Empty<AlbumAssetSummary>(), null, null);
    }

    public static AlbumAssetsResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new AlbumAssetsResult(false, false, Array.Empty<AlbumAssetSummary>(), statusCode, errorMessage);
    }
}
