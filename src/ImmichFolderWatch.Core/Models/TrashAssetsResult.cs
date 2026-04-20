using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class TrashAssetsResult
{
    private TrashAssetsResult(bool isSuccess, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static TrashAssetsResult Success()
    {
        return new TrashAssetsResult(true, null, null);
    }

    public static TrashAssetsResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new TrashAssetsResult(false, statusCode, errorMessage);
    }
}
