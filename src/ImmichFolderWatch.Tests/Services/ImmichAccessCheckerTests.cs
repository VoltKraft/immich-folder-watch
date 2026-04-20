using System.Net;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Immich;

namespace ImmichFolderWatch.Tests.Services;

public sealed class ImmichAccessCheckerTests
{
    [Fact]
    public async Task CheckAsync_ReturnsPassedWhenAllPermissionsAreAvailable()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, requireDownloadPermissions: true, CancellationToken.None);

        Assert.Equal(CheckState.Passed, result.UrlState);
        Assert.Equal(CheckState.Passed, result.ApiKeyState);
        Assert.Equal(CheckState.Passed, result.PermissionsState);
        Assert.All(result.PermissionResults, permission => Assert.Equal(CheckState.Passed, permission.State));
        Assert.Empty(result.GetBlockingErrors());
    }

    [Fact]
    public async Task CheckAsync_ReturnsFailedWhenApiKeyIsRejected()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.Unauthorized));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, CancellationToken.None);

        Assert.Equal(CheckState.Passed, result.UrlState);
        Assert.Equal(CheckState.Failed, result.ApiKeyState);
        Assert.Equal(CheckState.NotChecked, result.PermissionsState);
        Assert.All(result.PermissionResults, permission => Assert.Equal(CheckState.NotChecked, permission.State));
    }

    [Fact]
    public async Task CheckAsync_ReturnsFailedWhenAlbumPermissionsAreMissingAndAlbumPlacementIsRequired()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, CancellationToken.None);

        Assert.Equal(CheckState.Passed, result.UrlState);
        Assert.Equal(CheckState.Passed, result.ApiKeyState);
        Assert.Equal(CheckState.Failed, result.PermissionsState);
        Assert.Equal(CheckState.Passed, result.PermissionResults[0].State);
        Assert.All(result.PermissionResults.Skip(1), permission => Assert.Equal(CheckState.Failed, permission.State));
        Assert.Equal(3, result.GetBlockingErrors().Count);
    }

    [Fact]
    public async Task CheckAsync_ReturnsFailedWhenDownloadPermissionIsMissingAndSyncIsRequired()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.Forbidden));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, requireDownloadPermissions: true, CancellationToken.None);

        Assert.Equal(CheckState.Passed, result.UrlState);
        Assert.Equal(CheckState.Passed, result.ApiKeyState);
        Assert.Equal(CheckState.Failed, result.PermissionsState);
        var downloadPermission = result.PermissionResults.Single(permission => permission.PermissionName == "asset.download");
        Assert.Equal(CheckState.Failed, downloadPermission.State);
        Assert.True(downloadPermission.BlocksConfigVerification);
        Assert.Contains(result.GetBlockingErrors(), error => error.Contains("Asset Download", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CheckAsync_AllowsMissingDownloadPermission_WhenSyncIsNotRequired()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.Forbidden));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, requireDownloadPermissions: false, CancellationToken.None);

        Assert.Equal(CheckState.Passed, result.UrlState);
        Assert.Equal(CheckState.Passed, result.ApiKeyState);
        var downloadPermission = result.PermissionResults.Single(permission => permission.PermissionName == "asset.download");
        Assert.Equal(CheckState.Failed, downloadPermission.State);
        Assert.False(downloadPermission.BlocksConfigVerification);
        Assert.DoesNotContain(result.GetBlockingErrors(), error => error.Contains("Asset Download", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CheckAsync_ReturnsFailedWhenUploadPermissionIsMissing()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, CancellationToken.None);

        Assert.Equal(CheckState.Failed, result.PermissionsState);
        Assert.Equal(CheckState.Failed, result.PermissionResults[0].State);
        Assert.Contains(result.GetBlockingErrors(), error => error.Contains("Asset Upload", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CheckAsync_AllowsMissingAlbumPermissions_WhenNoAlbumPlacementIsRequired()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden));

        var result = await checker.CheckAsync(requireAlbumPermissions: false, CancellationToken.None);

        Assert.Equal(CheckState.Passed, result.UrlState);
        Assert.Equal(CheckState.Passed, result.ApiKeyState);
        Assert.Equal(CheckState.Passed, result.PermissionsState);
        Assert.Equal(CheckState.Passed, result.PermissionResults[0].State);
        Assert.All(result.PermissionResults.Skip(1), permission => Assert.Equal(CheckState.Failed, permission.State));
        Assert.Empty(result.GetBlockingErrors());
    }

    private static ImmichAccessChecker CreateChecker(params HttpResponseMessage[] responses)
    {
        var handler = new QueueHttpMessageHandler(responses);
        var httpClient = new HttpClient(handler)
        {
            BaseAddress = new Uri("https://immich.example.com/api/"),
        };

        httpClient.DefaultRequestHeaders.Add("x-api-key", "demo-key");
        return new ImmichAccessChecker(httpClient);
    }

    private static HttpResponseMessage CreateResponse(HttpStatusCode statusCode, string content = "")
    {
        return new HttpResponseMessage(statusCode)
        {
            Content = new StringContent(content),
        };
    }

    private sealed class QueueHttpMessageHandler : HttpMessageHandler
    {
        private readonly Queue<HttpResponseMessage> _responses;

        public QueueHttpMessageHandler(IEnumerable<HttpResponseMessage> responses)
        {
            _responses = new Queue<HttpResponseMessage>(responses);
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (_responses.Count == 0)
            {
                throw new InvalidOperationException($"No queued response available for {request.Method} {request.RequestUri}");
            }

            return Task.FromResult(_responses.Dequeue());
        }
    }
}
