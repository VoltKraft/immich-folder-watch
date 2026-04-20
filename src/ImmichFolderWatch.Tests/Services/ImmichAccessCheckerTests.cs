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
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, requireSyncPermissions: true, CancellationToken.None);

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
            CreateResponse(HttpStatusCode.Forbidden),
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
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, requireSyncPermissions: true, CancellationToken.None);

        Assert.Equal(CheckState.Passed, result.UrlState);
        Assert.Equal(CheckState.Passed, result.ApiKeyState);
        Assert.Equal(CheckState.Failed, result.PermissionsState);
        var downloadPermission = result.PermissionResults.Single(permission => permission.PermissionName == "asset.download");
        Assert.Equal(CheckState.Failed, downloadPermission.State);
        Assert.True(downloadPermission.BlocksConfigVerification);
        Assert.Contains(result.GetBlockingErrors(), error => error.Contains("Asset Download", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CheckAsync_ReturnsFailedWhenAssetReadPermissionIsMissingAndSyncIsRequired()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, requireSyncPermissions: true, CancellationToken.None);

        Assert.Equal(CheckState.Failed, result.PermissionsState);
        var assetReadPermission = result.PermissionResults.Single(permission => permission.PermissionName == "asset.read");
        Assert.Equal(CheckState.Failed, assetReadPermission.State);
        Assert.True(assetReadPermission.BlocksConfigVerification);
        Assert.Contains(result.GetBlockingErrors(), error => error.Contains("Asset Read", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CheckAsync_ReturnsFailedWhenAssetDeletePermissionIsMissingAndSyncIsRequired()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, requireSyncPermissions: true, CancellationToken.None);

        Assert.Equal(CheckState.Failed, result.PermissionsState);
        var assetDeletePermission = result.PermissionResults.Single(permission => permission.PermissionName == "asset.delete");
        Assert.Equal(CheckState.Failed, assetDeletePermission.State);
        Assert.True(assetDeletePermission.BlocksConfigVerification);
        Assert.Contains(result.GetBlockingErrors(), error => error.Contains("Asset Delete", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CheckAsync_ReturnsFailedWhenAlbumAssetDeletePermissionIsMissingAndSyncIsRequired()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.BadRequest));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, requireSyncPermissions: true, CancellationToken.None);

        Assert.Equal(CheckState.Failed, result.PermissionsState);
        var albumAssetDeletePermission = result.PermissionResults.Single(permission => permission.PermissionName == "albumAsset.delete");
        Assert.Equal(CheckState.Failed, albumAssetDeletePermission.State);
        Assert.True(albumAssetDeletePermission.BlocksConfigVerification);
        Assert.Contains(result.GetBlockingErrors(), error => error.Contains("Remove Asset From Album", StringComparison.Ordinal));
    }

    [Fact]
    public async Task CheckAsync_AllowsMissingSyncPermissions_WhenSyncIsNotRequired()
    {
        var checker = CreateChecker(
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.OK),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden),
            CreateResponse(HttpStatusCode.Forbidden));

        var result = await checker.CheckAsync(requireAlbumPermissions: true, requireSyncPermissions: false, CancellationToken.None);

        Assert.Equal(CheckState.Passed, result.UrlState);
        Assert.Equal(CheckState.Passed, result.ApiKeyState);
        foreach (var name in new[] { "asset.download", "asset.read", "asset.delete", "albumAsset.delete", "album.delete" })
        {
            var permission = result.PermissionResults.Single(p => p.PermissionName == name);
            Assert.Equal(CheckState.Failed, permission.State);
            Assert.False(permission.BlocksConfigVerification);
        }

        Assert.DoesNotContain(result.GetBlockingErrors(), error =>
            error.Contains("Asset Download", StringComparison.Ordinal)
            || error.Contains("Asset Read", StringComparison.Ordinal)
            || error.Contains("Asset Delete", StringComparison.Ordinal)
            || error.Contains("Remove Assets From Albums", StringComparison.Ordinal));
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
            CreateResponse(HttpStatusCode.BadRequest),
            CreateResponse(HttpStatusCode.BadRequest),
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
            CreateResponse(HttpStatusCode.Forbidden),
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
