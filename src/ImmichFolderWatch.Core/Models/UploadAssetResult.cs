using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class UploadAssetResult
{
    private UploadAssetResult(
        bool isSuccess,
        string? assetId,
        HttpStatusCode? statusCode,
        string? errorMessage,
        bool canRetry)
    {
        IsSuccess = isSuccess;
        AssetId = assetId;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
        CanRetry = canRetry;
    }

    public bool IsSuccess { get; }

    public string? AssetId { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public bool CanRetry { get; }

    public static UploadAssetResult Success(string? assetId)
    {
        return new UploadAssetResult(true, assetId, null, null, false);
    }

    public static UploadAssetResult Failure(
        HttpStatusCode? statusCode,
        string errorMessage,
        bool canRetry = false)
    {
        return new UploadAssetResult(false, null, statusCode, errorMessage, canRetry);
    }
}
