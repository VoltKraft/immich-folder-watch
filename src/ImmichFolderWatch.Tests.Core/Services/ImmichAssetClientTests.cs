using System.Globalization;
using System.Net;
using System.Text;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class ImmichAssetClientTests
{
    [Theory]
    [InlineData("\"fileModifiedAt\":\"2026-01-02T03:04:05Z\",\"fileCreatedAt\":\"2025-01-01T00:00:00Z\"")]
    [InlineData("\"fileModifiedAt\":\"invalid\",\"fileCreatedAt\":\"2026-01-02T03:04:05Z\"")]
    [InlineData("\"createdAt\":\"2026-01-02T03:04:05Z\"")]
    public async Task GetAlbumAssetsAsync_ParsesTimestampWithCreationFallback(string timestampJson)
    {
        var (client, _) = CreateClient(
            _ => CreateJsonResponse(HttpStatusCode.OK, "[{\"id\":\"album-1\",\"albumName\":\"Screenshots\"}]"),
            _ => CreateJsonResponse(HttpStatusCode.OK, "{\"assets\":{\"items\":[{\"id\":\"asset-1\",\"originalFileName\":\"photo.jpg\"," + timestampJson + "}],\"nextPage\":null}}"));

        var result = await client.GetAlbumAssetsAsync("Screenshots", CancellationToken.None);

        Assert.True(result.IsSuccess);
        Assert.Equal(new DateTimeOffset(2026, 1, 2, 3, 4, 5, TimeSpan.Zero), Assert.Single(result.Assets).FileModifiedAt);
    }

    [Theory]
    [InlineData("\"fileCreatedAt\":\"2020-02-03T14:15:16+02:00\",\"fileModifiedAt\":\"2024-01-01T00:00:00Z\"", "2020-02-03T12:15:16Z")]
    [InlineData("\"fileCreatedAt\":\"2020-02-03T12:15:16Z\",\"fileModifiedAt\":\"invalid\"", "2020-02-03T12:15:16Z")]
    [InlineData("\"fileCreatedAt\":\"invalid\",\"fileModifiedAt\":\"2024-01-01T00:00:00Z\"", null)]
    [InlineData("\"fileCreatedAt\":null,\"createdAt\":\"2024-01-01T00:00:00Z\"", null)]
    [InlineData("\"fileCreatedAt\":\"invalid\",\"createdAt\":\"2024-01-01T00:00:00Z\"", null)]
    [InlineData("\"createdAt\":\"2024-01-01T00:00:00Z\"", null)]
    public async Task GetAlbumAssetsAsync_ParsesOriginalCreationIndependentlyFromModificationAndUploadTime(
        string timestampJson, string? expectedCreation)
    {
        var (client, _) = CreateClient(
            _ => CreateJsonResponse(HttpStatusCode.OK, "[{\"id\":\"album-1\",\"albumName\":\"Screenshots\"}]"),
            _ => CreateJsonResponse(HttpStatusCode.OK, "{\"assets\":{\"items\":[{\"id\":\"asset-1\",\"originalFileName\":\"photo.jpg\"," + timestampJson + "}],\"nextPage\":null}}"));

        var result = await client.GetAlbumAssetsAsync("Screenshots", CancellationToken.None);

        Assert.True(result.IsSuccess);
        var asset = Assert.Single(result.Assets);
        Assert.Equal(expectedCreation is null ? (DateTimeOffset?)null
            : DateTimeOffset.Parse(expectedCreation, CultureInfo.InvariantCulture), asset.FileCreatedAt);
    }

    [Fact]
    public async Task GetUnassignedAssetsAsync_PreservesBothOriginalFileTimestamps()
    {
        var (client, _) = CreateClient(_ => CreateJsonResponse(HttpStatusCode.OK,
            "{\"assets\":{\"items\":[{\"id\":\"asset-1\",\"originalFileName\":\"photo.jpg\","
            + "\"fileCreatedAt\":\"2020-01-01T00:00:00Z\",\"fileModifiedAt\":\"2021-01-01T00:00:00Z\","
            + "\"createdAt\":\"2026-01-01T00:00:00Z\"}],\"nextPage\":null}}"));

        var result = await client.GetUnassignedAssetsAsync(CancellationToken.None);

        Assert.True(result.IsSuccess);
        var asset = Assert.Single(result.Assets);
        Assert.Equal(new DateTimeOffset(2020, 1, 1, 0, 0, 0, TimeSpan.Zero), asset.FileCreatedAt);
        Assert.Equal(new DateTimeOffset(2021, 1, 1, 0, 0, 0, TimeSpan.Zero), asset.FileModifiedAt);
    }

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

    [Theory]
    [InlineData(HttpStatusCode.BadRequest, false)]
    [InlineData(HttpStatusCode.RequestTimeout, true)]
    [InlineData(HttpStatusCode.TooManyRequests, true)]
    [InlineData(HttpStatusCode.ServiceUnavailable, true)]
    public async Task UploadAssetAttemptAsync_ClassifiesWhetherFailureCanBeRetried(
        HttpStatusCode statusCode,
        bool expectedCanRetry)
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(statusCode, "{\"message\":\"upload failed\"}"));

            var result = await client.UploadAssetAttemptAsync(
                new UploadAssetRequest(filePath, string.Empty),
                CancellationToken.None);

            Assert.False(result.IsSuccess);
            Assert.Equal(expectedCanRetry, result.CanRetry);
            Assert.Single(handler.Requests);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task UploadAssetAttemptAsync_ClassifiesTemporaryAlbumFailureAsRetryable()
    {
        var filePath = CreateTempFile();
        try
        {
            var (client, handler) = CreateClient(
                _ => CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"asset-1\"}"),
                _ => CreateJsonResponse(HttpStatusCode.ServiceUnavailable, "{\"message\":\"try later\"}"));

            var result = await client.UploadAssetAttemptAsync(
                new UploadAssetRequest(filePath, "Screenshots"),
                CancellationToken.None);

            Assert.False(result.IsSuccess);
            Assert.True(result.CanRetry);
            Assert.Equal(2, handler.Requests.Count);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task UploadAssetAttemptAsync_PropagatesCancellationDuringAlbumRequest()
    {
        var filePath = CreateTempFile();
        try
        {
            var handler = new AlbumCancellationHttpMessageHandler();
            using var httpClient = new HttpClient(handler) { BaseAddress = new Uri("https://immich.example.com/api/") };
            var client = new ImmichAssetClient(
                httpClient,
                new RetrySettings { MaxAttempts = 1, BaseDelayMilliseconds = 1 },
                NullLogger<ImmichAssetClient>.Instance);
            using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(250));

            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => client.UploadAssetAttemptAsync(
                new UploadAssetRequest(filePath, "Screenshots"),
                cancellation.Token));

            Assert.Equal(2, handler.RequestCount);
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

    private sealed class AlbumCancellationHttpMessageHandler : HttpMessageHandler
    {
        private int _requestCount;

        public int RequestCount => Volatile.Read(ref _requestCount);

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            var requestCount = Interlocked.Increment(ref _requestCount);
            if (requestCount == 1)
            {
                return CreateJsonResponse(HttpStatusCode.Created, "{\"id\":\"asset-1\"}");
            }

            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            throw new InvalidOperationException("The cancellation-aware delay should not complete normally.");
        }
    }

    private sealed record RecordedRequest(HttpMethod Method, string PathAndQuery, string Body);
}
