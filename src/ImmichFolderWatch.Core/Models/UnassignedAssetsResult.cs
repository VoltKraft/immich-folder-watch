using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class UnassignedAssetsResult
{
    private UnassignedAssetsResult(bool isSuccess, IReadOnlyList<AlbumAssetSummary> assets, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        Assets = assets;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public IReadOnlyList<AlbumAssetSummary> Assets { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static UnassignedAssetsResult Success(IReadOnlyList<AlbumAssetSummary> assets)
    {
        return new UnassignedAssetsResult(true, assets, null, null);
    }

    public static UnassignedAssetsResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new UnassignedAssetsResult(false, Array.Empty<AlbumAssetSummary>(), statusCode, errorMessage);
    }
}
