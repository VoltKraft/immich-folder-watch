using System.Net;
using System.Text;
using ImmichFolderWatch.Core.Services;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class GitHubUpdateCheckerTests
{
    private const string LatestReleaseUrl = "https://api.github.com/repos/VoltKraft/immich-folder-watch/releases/latest";

    [Fact]
    public async Task CheckAsync_ReturnsUpdate_WhenReleaseIsNewer()
    {
        const string tag = "v2.8.0";
        var (checker, handler, logger) = CreateChecker(CreateReleaseResponse(tag));

        var result = await checker.CheckAsync(new Version(2, 7, 0), CancellationToken.None);

        Assert.NotNull(result);
        Assert.Equal(new Version(2, 8, 0), result.Version);
        Assert.Equal(new Uri($"https://github.com/VoltKraft/immich-folder-watch/releases/tag/{tag}"), result.DownloadUri);
        Assert.Empty(logger.Entries);
        Assert.Single(handler.Requests);
    }

    [Theory]
    [InlineData("v2.7.0")]
    [InlineData("v2.6.9")]
    public async Task CheckAsync_ReturnsNull_WhenReleaseIsNotNewer(string tag)
    {
        var (checker, handler, logger) = CreateChecker(CreateReleaseResponse(tag));

        var result = await checker.CheckAsync(new Version(2, 7, 0, 0), CancellationToken.None);

        Assert.Null(result);
        Assert.Empty(logger.Entries);
        Assert.Single(handler.Requests);
    }

    [Fact]
    public async Task CheckAsync_SendsAnonymousGitHubRequestWithRequiredHeaders()
    {
        var (checker, handler, _) = CreateChecker(CreateReleaseResponse("v2.8.0"));

        await checker.CheckAsync(new Version(2, 7, 0), CancellationToken.None);

        var request = Assert.Single(handler.Requests);
        Assert.Equal(HttpMethod.Get, request.Method);
        Assert.Equal(new Uri(LatestReleaseUrl), request.Uri);
        Assert.Contains("application/vnd.github+json", request.Accept);
        Assert.Contains("ImmichFolderWatch/2.7.0", request.UserAgent);
        Assert.DoesNotContain(request.Headers.Keys, name =>
            string.Equals(name, "Authorization", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(request.Headers.Keys, name =>
            string.Equals(name, "x-api-key", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(request.Headers.Keys, name =>
            name.StartsWith("Immich", StringComparison.OrdinalIgnoreCase));
    }

    [Theory]
    [InlineData("v2.8")]
    [InlineData("2.8.0")]
    [InlineData("v2.8.0-beta.1")]
    [InlineData("v02.8.0")]
    [InlineData("release-2.8.0")]
    public async Task CheckAsync_LogsOnceAndReturnsNull_WhenTagIsInvalid(string tag)
    {
        var (checker, _, logger) = CreateChecker(CreateReleaseResponse(tag));

        var result = await checker.CheckAsync(new Version(2, 7, 0), CancellationToken.None);

        Assert.Null(result);
        AssertSingleWarning(logger);
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("{\"tag_name\":\"v2.8.0\"}")]
    [InlineData("{\"tag_name\":null,\"html_url\":\"https://github.com/VoltKraft/immich-folder-watch/releases/tag/2.8.0\"}")]
    [InlineData("not json")]
    public async Task CheckAsync_LogsOnceAndReturnsNull_WhenResponseIsInvalid(string json)
    {
        var (checker, _, logger) = CreateChecker(CreateJsonResponse(HttpStatusCode.OK, json));

        var result = await checker.CheckAsync(new Version(2, 7, 0), CancellationToken.None);

        Assert.Null(result);
        AssertSingleWarning(logger);
    }

    [Theory]
    [InlineData("http://github.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0")]
    [InlineData("https://example.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0")]
    [InlineData("https://github.com/VoltKraft/other/releases/tag/v2.8.0")]
    [InlineData("https://github.com/VoltKraft/immich-folder-watch/releases/tag/2.8.0")]
    [InlineData("not-a-url")]
    public async Task CheckAsync_LogsOnceAndReturnsNull_WhenDownloadUrlIsUnexpected(string htmlUrl)
    {
        var response = CreateJsonResponse(
            HttpStatusCode.OK,
            $"{{\"tag_name\":\"v2.8.0\",\"html_url\":\"{htmlUrl}\"}}");
        var (checker, _, logger) = CreateChecker(response);

        var result = await checker.CheckAsync(new Version(2, 7, 0), CancellationToken.None);

        Assert.Null(result);
        AssertSingleWarning(logger);
    }

    [Theory]
    [InlineData("draft")]
    [InlineData("prerelease")]
    public async Task CheckAsync_LogsOnceAndReturnsNull_WhenReleaseIsNotStable(string propertyName)
    {
        var json = $"{{\"tag_name\":\"v2.8.0\",\"html_url\":\"https://github.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0\",\"{propertyName}\":true}}";
        var (checker, _, logger) = CreateChecker(CreateJsonResponse(HttpStatusCode.OK, json));

        var result = await checker.CheckAsync(new Version(2, 7, 0), CancellationToken.None);

        Assert.Null(result);
        AssertSingleWarning(logger);
    }

    [Theory]
    [InlineData(HttpStatusCode.Found)]
    [InlineData(HttpStatusCode.ServiceUnavailable)]
    public async Task CheckAsync_LogsOnceAndReturnsNull_WhenHttpStatusIsUnsuccessful(HttpStatusCode statusCode)
    {
        var (checker, _, logger) = CreateChecker(new HttpResponseMessage(statusCode));

        var result = await checker.CheckAsync(new Version(2, 7, 0), CancellationToken.None);

        Assert.Null(result);
        AssertSingleWarning(logger);
    }

    [Fact]
    public async Task CheckAsync_LogsOnceAndReturnsNull_WhenRequestFails()
    {
        var (checker, _, logger) = CreateChecker(
            (Func<CancellationToken, HttpResponseMessage>)(_ => throw new HttpRequestException("Network unavailable.")));

        var result = await checker.CheckAsync(new Version(2, 7, 0), CancellationToken.None);

        Assert.Null(result);
        AssertSingleWarning(logger);
    }

    [Fact]
    public async Task CheckAsync_LogsOnceAndReturnsNull_WhenRequestTimesOut()
    {
        var (checker, _, logger) = CreateChecker(async cancellationToken =>
        {
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            return CreateReleaseResponse("v2.8.0");
        }, TimeSpan.FromMilliseconds(20));

        var result = await checker.CheckAsync(new Version(2, 7, 0), CancellationToken.None);

        Assert.Null(result);
        AssertSingleWarning(logger);
    }

    [Fact]
    public async Task CheckAsync_PropagatesExternalCancellationWithoutLogging()
    {
        using var cancellationSource = new CancellationTokenSource();
        cancellationSource.Cancel();
        var (checker, _, logger) = CreateChecker(CreateReleaseResponse("v2.8.0"));

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            checker.CheckAsync(new Version(2, 7, 0), cancellationSource.Token));

        Assert.Empty(logger.Entries);
    }

    private static (GitHubUpdateChecker Checker, RecordingHttpMessageHandler Handler, RecordingLogger<GitHubUpdateChecker> Logger) CreateChecker(
        HttpResponseMessage response,
        TimeSpan? timeout = null)
    {
        return CreateChecker(_ => Task.FromResult(response), timeout);
    }

    private static (GitHubUpdateChecker Checker, RecordingHttpMessageHandler Handler, RecordingLogger<GitHubUpdateChecker> Logger) CreateChecker(
        Func<CancellationToken, HttpResponseMessage> responseFactory,
        TimeSpan? timeout = null)
    {
        return CreateChecker(token => Task.FromResult(responseFactory(token)), timeout);
    }

    private static (GitHubUpdateChecker Checker, RecordingHttpMessageHandler Handler, RecordingLogger<GitHubUpdateChecker> Logger) CreateChecker(
        Func<CancellationToken, Task<HttpResponseMessage>> responseFactory,
        TimeSpan? timeout = null)
    {
        var handler = new RecordingHttpMessageHandler(responseFactory);
        var httpClient = new HttpClient(handler);
        if (timeout.HasValue)
        {
            httpClient.Timeout = timeout.Value;
        }

        var logger = new RecordingLogger<GitHubUpdateChecker>();
        return (new GitHubUpdateChecker(httpClient, logger), handler, logger);
    }

    private static HttpResponseMessage CreateReleaseResponse(string tag)
    {
        return CreateJsonResponse(
            HttpStatusCode.OK,
            $"{{\"tag_name\":\"{tag}\",\"html_url\":\"https://github.com/VoltKraft/immich-folder-watch/releases/tag/{tag}\",\"draft\":false,\"prerelease\":false}}");
    }

    private static HttpResponseMessage CreateJsonResponse(HttpStatusCode statusCode, string json)
    {
        return new HttpResponseMessage(statusCode)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json"),
        };
    }

    private static void AssertSingleWarning(RecordingLogger<GitHubUpdateChecker> logger)
    {
        var entry = Assert.Single(logger.Entries);
        Assert.Equal(LogLevel.Warning, entry.Level);
        Assert.NotNull(entry.Exception);
    }

    private sealed class RecordingHttpMessageHandler : HttpMessageHandler
    {
        private readonly Func<CancellationToken, Task<HttpResponseMessage>> _responseFactory;

        public RecordingHttpMessageHandler(Func<CancellationToken, Task<HttpResponseMessage>> responseFactory)
        {
            _responseFactory = responseFactory;
        }

        public List<RecordedRequest> Requests { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests.Add(new RecordedRequest(
                request.Method,
                request.RequestUri,
                request.Headers.Accept.Select(value => value.MediaType ?? string.Empty).ToArray(),
                request.Headers.UserAgent.ToString(),
                request.Headers.ToDictionary(header => header.Key, header => header.Value.ToArray(), StringComparer.OrdinalIgnoreCase)));

            return await _responseFactory(cancellationToken);
        }
    }

    private sealed record RecordedRequest(
        HttpMethod Method,
        Uri? Uri,
        IReadOnlyList<string> Accept,
        string UserAgent,
        IReadOnlyDictionary<string, string[]> Headers);

    private sealed class RecordingLogger<T> : ILogger<T>
    {
        public List<LogEntry> Entries { get; } = new();

        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull
        {
            return null;
        }

        public bool IsEnabled(LogLevel logLevel)
        {
            return true;
        }

        public void Log<TState>(
            LogLevel logLevel,
            EventId eventId,
            TState state,
            Exception? exception,
            Func<TState, Exception?, string> formatter)
        {
            Entries.Add(new LogEntry(logLevel, exception, formatter(state, exception)));
        }
    }

    private sealed record LogEntry(LogLevel Level, Exception? Exception, string Message);
}
