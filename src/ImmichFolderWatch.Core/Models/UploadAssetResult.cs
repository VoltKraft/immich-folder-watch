using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class UploadAssetResult
{
    private UploadAssetResult(bool isSuccess, string? assetId, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        AssetId = assetId;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public string? AssetId { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static UploadAssetResult Success(string? assetId)
    {
        return new UploadAssetResult(true, assetId, null, null);
    }

    public static UploadAssetResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new UploadAssetResult(false, null, statusCode, errorMessage);
    }
}
