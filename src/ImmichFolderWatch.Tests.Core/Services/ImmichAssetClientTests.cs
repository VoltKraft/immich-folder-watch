using System.Net;
using System.Text;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class ImmichAssetClientTests
{
    [Fact]
    public async Task UploadAssetAsync_AddsAssetToExistingAlbum()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"asset-1\"}"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "[{\"id\":\"album-1\",\"albumName\":\"Screenshots\"}]"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "{}"));

            var result = await client.UploadAssetAsync(new UploadAssetRequest(filePath, "Screenshots"), CancellationToken.None);

            Assert.True(result.IsSuccess);
            Assert.Equal("asset-1", result.AssetId);
            Assert.Collection(
                handler.Requests,
                request =>
                {
                    Assert.Equal(HttpMethod.Post, request.Method);
                    Assert.EndsWith("/api/assets", request.PathAndQuery, StringComparison.Ordinal);
                    Assert.Contains("filename", request.Body, StringComparison.Ordinal);
                    Assert.DoesNotContain("deviceAssetId", request.Body, StringComparison.Ordinal);
                    Assert.DoesNotContain("deviceId", request.Body, StringComparison.Ordinal);
                    Assert.DoesNotContain("isArchived", request.Body, StringComparison.Ordinal);
                },
                request =>
                {
                    Assert.Equal(HttpMethod.Get, request.Method);
                    Assert.EndsWith("/api/albums", request.PathAndQuery, StringComparison.Ordinal);
                },
                request =>
                {
                    Assert.Equal(HttpMethod.Put, request.Method);
                    Assert.EndsWith("/api/albums/album-1/assets", request.PathAndQuery, StringComparison.Ordinal);
                    Assert.Contains("\"ids\":[\"asset-1\"]", request.Body, StringComparison.Ordinal);
                });
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task UploadAssetAsync_CreatesAlbumWhenMissing()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"asset-1\"}"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "[]"),
                _ => CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"album-1\",\"albumName\":\"Screenshots\"}"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "{}"));

            var result = await client.UploadAssetAsync(new UploadAssetRequest(filePath, "Screenshots"), CancellationToken.None);

            Assert.True(result.IsSuccess);
            Assert.Equal(4, handler.Requests.Count);
            Assert.Equal(HttpMethod.Post, handler.Requests[2].Method);
            Assert.EndsWith("/api/albums", handler.Requests[2].PathAndQuery, StringComparison.Ordinal);
            Assert.Contains("\"albumName\":\"Screenshots\"", handler.Requests[2].Body, StringComparison.Ordinal);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task UploadAssetAsync_SkipsAlbumAssignmentWhenAlbumNameIsEmpty()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"asset-1\"}"));

            var result = await client.UploadAssetAsync(new UploadAssetRequest(filePath, "   "), CancellationToken.None);

            Assert.True(result.IsSuccess);
            Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, handler.Requests[0].Method);
            Assert.EndsWith("/api/assets", handler.Requests[0].PathAndQuery, StringComparison.Ordinal);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task UploadAssetAsync_RetriesWithLegacyIdentifiersWhenModernUploadPayloadIsRejected()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.UnprocessableEntity, "{\"message\":[\"deviceAssetId must be a string\",\"deviceId must be a string\"]}"),
                _ => CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"asset-1\"}"));

            var result = await client.UploadAssetAsync(new UploadAssetRequest(filePath, "   "), CancellationToken.None);

            Assert.True(result.IsSuccess);
            Assert.Equal("asset-1", result.AssetId);
            Assert.Equal(2, handler.Requests.Count);
            Assert.All(handler.Requests, request => Assert.EndsWith("/api/assets", request.PathAndQuery, StringComparison.Ordinal));
            Assert.DoesNotContain("deviceAssetId", handler.Requests[0].Body, StringComparison.Ordinal);
            Assert.DoesNotContain("deviceId", handler.Requests[0].Body, StringComparison.Ordinal);
            Assert.Contains("deviceAssetId", handler.Requests[1].Body, StringComparison.Ordinal);
            Assert.Contains("deviceId", handler.Requests[1].Body, StringComparison.Ordinal);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task UploadAssetAsync_DoesNotRetryWithLegacyIdentifiersForUnrelatedValidationErrors()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.UnprocessableEntity, "{\"message\":\"Validation failed\"}"));

            var result = await client.UploadAssetAsync(new UploadAssetRequest(filePath, "   "), CancellationToken.None);

            Assert.False(result.IsSuccess);
            Assert.Single(handler.Requests);
            Assert.DoesNotContain("deviceAssetId", handler.Requests[0].Body, StringComparison.Ordinal);
            Assert.DoesNotContain("deviceId", handler.Requests[0].Body, StringComparison.Ordinal);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task UploadAssetAsync_FailsWhenDuplicateAlbumNamesExist()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"asset-1\"}"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "[{\"id\":\"album-1\",\"albumName\":\"Screenshots\"},{\"id\":\"album-2\",\"albumName\":\"Screenshots\"}]"));

            var result = await client.UploadAssetAsync(new UploadAssetRequest(filePath, "Screenshots"), CancellationToken.None);

            Assert.False(result.IsSuccess);
            Assert.Contains("Multiple Immich albums named 'Screenshots' already exist.", result.ErrorMessage, StringComparison.Ordinal);
            Assert.Equal(2, handler.Requests.Count);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task UploadAssetAsync_RequeriesAlbumAfterCreateConflict()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"asset-1\"}"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "[]"),
                _ => CreateJsonResponse(HttpStatusCode.Conflict, "{\"message\":\"already exists\"}"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "[{\"id\":\"album-1\",\"albumName\":\"Screenshots\"}]"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "{}"));

            var result = await client.UploadAssetAsync(new UploadAssetRequest(filePath, "Screenshots"), CancellationToken.None);

            Assert.True(result.IsSuccess);
            Assert.Equal(5, handler.Requests.Count);
            Assert.Equal(HttpMethod.Get, handler.Requests[3].Method);
            Assert.EndsWith("/api/albums", handler.Requests[3].PathAndQuery, StringComparison.Ordinal);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task GetAlbumAssetsAsync_UsesMetadataSearchBecauseV3AlbumResponsesDoNotContainAssets()
    {
        var (client, handler) = CreateClient(
            _ => CreateJsonResponse(HttpStatusCode.OK, "[{\"id\":\"album-1\",\"albumName\":\"Screenshots\"}]"),
            _ => CreateJsonResponse(HttpStatusCode.OK, "{\"assets\":{\"items\":[{\"id\":\"asset-1\",\"originalFileName\":\"photo.jpg\"}],\"nextPage\":null}}"));

        var result = await client.GetAlbumAssetsAsync("Screenshots", CancellationToken.None);

        Assert.True(result.IsSuccess);
        Assert.Collection(
            result.Assets,
            asset =>
            {
                Assert.Equal("asset-1", asset.Id);
                Assert.Equal("photo.jpg", asset.OriginalFileName);
            });
        Assert.Collection(
            handler.Requests,
            request =>
            {
                Assert.Equal(HttpMethod.Get, request.Method);
                Assert.EndsWith("/api/albums", request.PathAndQuery, StringComparison.Ordinal);
            },
            request =>
            {
                Assert.Equal(HttpMethod.Post, request.Method);
                Assert.EndsWith("/api/search/metadata", request.PathAndQuery, StringComparison.Ordinal);
                Assert.Contains("\"albumIds\":[\"album-1\"]", request.Body, StringComparison.Ordinal);
                Assert.Contains("\"page\":1", request.Body, StringComparison.Ordinal);
                Assert.Contains("\"size\":250", request.Body, StringComparison.Ordinal);
            });
    }

    [Fact]
    public async Task UploadAssetAsync_UsesFallbackAlbumAssignmentRouteWhenPrimaryRouteIsUnavailable()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"asset-1\"}"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "[{\"id\":\"album-1\",\"albumName\":\"Screenshots\"}]"),
                _ => CreateJsonResponse(HttpStatusCode.NotFound, "{}"),
                _ => CreateJsonResponse(HttpStatusCode.OK, "{}"));

            var result = await client.UploadAssetAsync(new UploadAssetRequest(filePath, "Screenshots"), CancellationToken.None);

            Assert.True(result.IsSuccess);
            Assert.Equal(4, handler.Requests.Count);
            Assert.Equal(HttpMethod.Put, handler.Requests[3].Method);
            Assert.EndsWith("/api/albums/assets", handler.Requests[3].PathAndQuery, StringComparison.Ordinal);
            Assert.Contains("\"albumIds\":[\"album-1\"]", handler.Requests[3].Body, StringComparison.Ordinal);
            Assert.Contains("\"assetIds\":[\"asset-1\"]", handler.Requests[3].Body, StringComparison.Ordinal);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task UploadAssetAsync_FailsWhenAlbumPlacementNeedsAnAssetIdButImmichDidNotReturnOne()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.Created, "{}"));

            var result = await client.UploadAssetAsync(new UploadAssetRequest(filePath, "Screenshots"), CancellationToken.None);

            Assert.False(result.IsSuccess);
            Assert.Contains("did not return an asset id", result.ErrorMessage, StringComparison.Ordinal);
            Assert.Single(handler.Requests);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    private static (ImmichAssetClient Client, RecordingHttpMessageHandler Handler) CreateClient(params Func<HttpRequestMessage, HttpResponseMessage>[] responders)
    {
        var handler = new RecordingHttpMessageHandler(responders);
        var httpClient = new HttpClient(handler)
        {
            BaseAddress = new Uri("https://immich.example.com/api/"),
        };

        httpClient.DefaultRequestHeaders.Add("x-api-key", "demo-key");

        var client = new ImmichAssetClient(
            httpClient,
            new RetrySettings
            {
                MaxAttempts = 1,
                BaseDelayMilliseconds = 1,
            },
            NullLogger<ImmichAssetClient>.Instance);

        return (client, handler);
    }

    private static HttpResponseMessage CreateJsonResponse(HttpStatusCode statusCode, string json)
    {
        return new HttpResponseMessage(statusCode)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json"),
        };
    }

    private static string CreateTempFile()
    {
        var filePath = Path.Combine(Path.GetTempPath(), $"ifw-test-{Guid.NewGuid():N}.png");
        File.WriteAllBytes(filePath, [1, 2, 3, 4]);
        return filePath;
    }

    private sealed class RecordingHttpMessageHandler : HttpMessageHandler
    {
        private readonly Queue<Func<HttpRequestMessage, HttpResponseMessage>> _responders;

        public RecordingHttpMessageHandler(IEnumerable<Func<HttpRequestMessage, HttpResponseMessage>> responders)
        {
            _responders = new Queue<Func<HttpRequestMessage, HttpResponseMessage>>(responders);
        }

        public List<RecordedRequest> Requests { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (_responders.Count == 0)
            {
                throw new InvalidOperationException($"No queued response available for {request.Method} {request.RequestUri}");
            }

            var body = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);

            Requests.Add(new RecordedRequest(request.Method, request.RequestUri?.PathAndQuery ?? string.Empty, body));
            return _responders.Dequeue()(request);
        }
    }

    private sealed record RecordedRequest(HttpMethod Method, string PathAndQuery, string Body);
}
