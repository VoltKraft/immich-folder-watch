using System.Net;

namespace ImmichFolderWatch.Core.Models;

public sealed class AlbumMembershipUpdateResult
{
    private AlbumMembershipUpdateResult(bool isSuccess, HttpStatusCode? statusCode, string? errorMessage)
    {
        IsSuccess = isSuccess;
        StatusCode = statusCode;
        ErrorMessage = errorMessage;
    }

    public bool IsSuccess { get; }

    public HttpStatusCode? StatusCode { get; }

    public string? ErrorMessage { get; }

    public static AlbumMembershipUpdateResult Success()
    {
        return new AlbumMembershipUpdateResult(true, null, null);
    }

    public static AlbumMembershipUpdateResult Failure(HttpStatusCode? statusCode, string errorMessage)
    {
        return new AlbumMembershipUpdateResult(false, statusCode, errorMessage);
    }
}
