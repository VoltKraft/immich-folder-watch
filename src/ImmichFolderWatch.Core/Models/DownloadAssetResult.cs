using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class DownloadAssetResult
{
    private DownloadAssetResult(bool isSuccess, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static DownloadAssetResult Success()
    {
        return new DownloadAssetResult(true, null, null);
    }

    public static DownloadAssetResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new DownloadAssetResult(false, statusCode, errorMessage);
    }
}
