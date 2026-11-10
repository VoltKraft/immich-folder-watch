using System.Net;
using System.IO.Compression;
using System.Text;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class ImmichTransferSecurityTests
{
    [Fact]
    public async Task Upload_RejectsLinkedLeafBeforeOpeningOrSendingIt()
    {
        if (OperatingSystem.IsWindows()) return;
        using var directory = new TestDirectory();
        using var outside = new TestDirectory();
        var target = Path.Combine(outside.Path, "private.jpg");
        await File.WriteAllTextAsync(target, "private media");
        var linked = Path.Combine(directory.Path, "photo.jpg");
        File.CreateSymbolicLink(linked, target);
        var requests = 0;
        using var http = CreateHttp(_ => { requests++; return Json("{\"id\":\"asset\"}"); });

        var result = await CreateClient(http).UploadAssetAsync(new UploadAssetRequest(linked, "", directory.Path), CancellationToken.None);

        Assert.False(result.IsSuccess);
        Assert.Equal(0, requests);
        Assert.Equal("private media", await File.ReadAllTextAsync(target));
    }

    [Fact]
    public async Task Metadata_CountsBytesAfterDecompression()
    {
        using var compressed = new MemoryStream();
        using (var gzip = new GZipStream(compressed, CompressionMode.Compress, leaveOpen: true))
        {
            gzip.Write(new byte[1024 * 1024]);
        }

        compressed.Position = 0;
        // HttpClient automatic decompression exposes this expanded stream to the reader.
        using var http = CreateHttp(_ => StreamResponse(new GZipStream(compressed, CompressionMode.Decompress)));
        var result = await CreateClient(http, new() { MaxMetadataBytes = 4096 }).ListAlbumsAsync(CancellationToken.None);
        Assert.False(result.IsSuccess);
        Assert.Contains("metadata size limit", result.ErrorMessage);
    }

    [Fact]
    public async Task Download_IgnoresPredictableStagingSymlinkWithoutTouchingItsTarget()
    {
        if (OperatingSystem.IsWindows()) return; // Creating symlinks requires an elevated Windows privilege.
        using var directory = new TestDirectory();
        var destination = Path.Combine(directory.Path, "photo.jpg");
        var target = Path.Combine(directory.Path, "private.txt");
        await File.WriteAllTextAsync(target, "keep");
        File.CreateSymbolicLink(destination + ".downloading", target);
        using var http = CreateHttp(_ => Bytes([1, 2, 3]));

        var result = await CreateClient(http).DownloadAssetAsync("asset", destination, CancellationToken.None);

        Assert.True(result.IsSuccess, result.ErrorMessage);
        Assert.Equal("keep", await File.ReadAllTextAsync(target));
        Assert.NotNull(new FileInfo(destination + ".downloading").LinkTarget);
        Assert.Equal(new byte[] { 1, 2, 3 }, await File.ReadAllBytesAsync(destination));
        Assert.Single(Directory.GetFiles(directory.Path, "*.downloading"));
    }

    [Fact]
    public async Task Download_LeavesPredictableRegularStagingFileUntouched()
    {
        using var directory = new TestDirectory();
        var destination = Path.Combine(directory.Path, "photo.jpg");
        await File.WriteAllTextAsync(destination + ".downloading", "keep");
        using var http = CreateHttp(_ => Bytes([1]));

        var result = await CreateClient(http).DownloadAssetAsync("asset", destination, CancellationToken.None);

        Assert.True(result.IsSuccess, result.ErrorMessage);
        Assert.Equal("keep", await File.ReadAllTextAsync(destination + ".downloading"));
    }

    [Fact]
    public async Task Download_PreservesDestinationCreatedDuringTransfer()
    {
        using var directory = new TestDirectory();
        var destination = Path.Combine(directory.Path, "photo.jpg");
        var input = new GeneratedStream(32, onRead: () => File.WriteAllText(destination, "local media"));
        using var http = CreateHttp(_ => StreamResponse(input));

        var result = await CreateClient(http).DownloadAssetAsync("asset", destination, CancellationToken.None);

        Assert.False(result.IsSuccess);
        Assert.Equal("local media", await File.ReadAllTextAsync(destination));
        Assert.Empty(Directory.GetFiles(directory.Path, "*.downloading"));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Download_RejectsDeclaredAndStreamingOversizeAndRemovesPartial(bool declareLength)
    {
        using var directory = new TestDirectory();
        var destination = Path.Combine(directory.Path, "photo.jpg");
        var input = new GeneratedStream(1024);
        using var http = CreateHttp(_ => StreamResponse(input, declareLength ? 1024 : null));

        var result = await CreateClient(http, new() { MaxDownloadBytes = 16 }).DownloadAssetAsync("asset", destination, CancellationToken.None);

        Assert.False(result.IsSuccess);
        Assert.Contains("size limit", result.ErrorMessage);
        Assert.False(File.Exists(destination));
        Assert.Empty(Directory.GetFiles(directory.Path));
        if (declareLength) Assert.Equal(0, input.BytesRead);
    }

    [Fact]
    public async Task Download_PreservesFreeSpaceReserveBeforeReadingBody()
    {
        using var directory = new TestDirectory();
        var input = new GeneratedStream(32);
        using var http = CreateHttp(_ => StreamResponse(input));

        var result = await CreateClient(http, new() { MinimumFreeSpaceBytes = long.MaxValue })
            .DownloadAssetAsync("asset", Path.Combine(directory.Path, "photo.jpg"), CancellationToken.None);

        Assert.False(result.IsSuccess);
        Assert.Contains("free-space reserve", result.ErrorMessage);
        Assert.Equal(0, input.BytesRead);
        Assert.Empty(Directory.GetFiles(directory.Path));
    }

    [Fact]
    public async Task Download_CancellationCleansPartialAndPropagatesCancellation()
    {
        using var directory = new TestDirectory();
        using var canceled = new CancellationTokenSource();
        var input = new GeneratedStream(32, onRead: canceled.Cancel);
        using var http = CreateHttp(_ => StreamResponse(input));

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => CreateClient(http)
            .DownloadAssetAsync("asset", Path.Combine(directory.Path, "photo.jpg"), canceled.Token));

        Assert.Empty(Directory.GetFiles(directory.Path));
    }

    [Fact]
    public async Task Download_InactivityTimeoutCleansPartial()
    {
        using var directory = new TestDirectory();
        using var http = CreateHttp(_ => StreamResponse(new StallingStream()));

        var result = await CreateClient(http, new() { BodyInactivityTimeout = TimeSpan.FromMilliseconds(30) })
            .DownloadAssetAsync("asset", Path.Combine(directory.Path, "photo.jpg"), CancellationToken.None);

        Assert.False(result.IsSuccess);
        Assert.Empty(Directory.GetFiles(directory.Path));
    }

    [Fact]
    public async Task Download_RejectsTruncatedDeclaredBody()
    {
        using var directory = new TestDirectory();
        using var http = CreateHttp(_ => StreamResponse(new GeneratedStream(2), 5));
        var result = await CreateClient(http).DownloadAssetAsync("asset", Path.Combine(directory.Path, "photo.jpg"), CancellationToken.None);
        Assert.False(result.IsSuccess);
        Assert.Contains("declared length", result.ErrorMessage);
        Assert.Empty(Directory.GetFiles(directory.Path));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Metadata_RejectsDeclaredAndStreamingOversizeWithoutBufferingWholeBody(bool declareLength)
    {
        var input = new GeneratedStream(1024 * 1024);
        using var http = CreateHttp(_ => StreamResponse(input, declareLength ? 1024 * 1024 : null));

        var result = await CreateClient(http, new() { MaxMetadataBytes = 32 }).ListAlbumsAsync(CancellationToken.None);

        Assert.False(result.IsSuccess);
        Assert.Contains("metadata size limit", result.ErrorMessage);
        Assert.InRange(input.BytesRead, 0, declareLength ? 0 : 33);
    }

    [Fact]
    public async Task ErrorResponse_ReadsOnlyBoundedDiagnosticPrefix()
    {
        var input = new GeneratedStream(1024 * 1024);
        using var http = CreateHttp(_ => StreamResponse(input, status: HttpStatusCode.InternalServerError));

        var result = await CreateClient(http, new() { MaxDiagnosticBytes = 32 }).ListAlbumsAsync(CancellationToken.None);

        Assert.False(result.IsSuccess);
        Assert.Equal(32, input.BytesRead);
    }

    [Fact]
    public async Task AccessChecker_ReadsOnlyBoundedDiagnosticPrefixes()
    {
        var inputs = new List<GeneratedStream>();
        using var http = CreateHttp(_ =>
        {
            var input = new GeneratedStream(1024 * 1024);
            inputs.Add(input);
            return StreamResponse(input, status: HttpStatusCode.InternalServerError);
        });

        var result = await new ImmichAccessChecker(http).CheckAsync(false, CancellationToken.None);

        Assert.Equal(CheckState.Failed, result.UrlState);
        Assert.NotEmpty(inputs);
        Assert.All(inputs, input => Assert.Equal(64 * 1024, input.BytesRead));
    }

    [Fact]
    public async Task Search_Page500WithContinuationIsFailureWithoutPartialAssets()
    {
        var page = 0;
        using var http = CreateHttp(_ => Json($"{{\"assets\":{{\"items\":[{{\"id\":\"asset-{++page}\"}}],\"nextPage\":{page + 1}}}}}"));

        var result = await CreateClient(http).GetUnassignedAssetsAsync(CancellationToken.None);

        Assert.False(result.IsSuccess);
        Assert.Empty(result.Assets);
        Assert.Equal(500, page);
    }

    [Theory]
    [InlineData("{\"assets\":{\"items\":[],\"nextPage\":2}}")]
    [InlineData("{\"assets\":{\"items\":[{}],\"nextPage\":null}}")]
    [InlineData("{\"assets\":{\"items\":[{\"id\":\"a\"}],\"nextPage\":1}}")]
    [InlineData("{\"assets\":{\"items\":[{\"id\":\"a\"}],\"nextPage\":\"broken\"}}")]
    [InlineData("{\"items\":[],\"nextPage\":2}")]
    [InlineData("")]
    public async Task Search_RejectsContradictoryOrMalformedSnapshots(string json)
    {
        using var http = CreateHttp(_ => Json(json));
        var result = await CreateClient(http).GetUnassignedAssetsAsync(CancellationToken.None);
        Assert.False(result.IsSuccess);
        Assert.Empty(result.Assets);
    }

    [Fact]
    public async Task Search_CompletePaginationPreservesAssets()
    {
        var page = 0;
        using var http = CreateHttp(_ => Json(++page == 1
            ? "{\"assets\":{\"items\":[{\"id\":\"a\"}],\"nextPage\":\"2\"}}"
            : "{\"assets\":{\"items\":[{\"id\":\"b\"}],\"nextPage\":null}}"));
        var result = await CreateClient(http).GetUnassignedAssetsAsync(CancellationToken.None);
        Assert.True(result.IsSuccess, result.ErrorMessage);
        Assert.Equal(new[] { "a", "b" }, result.Assets.Select(asset => asset.Id));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Search_RejectsAggregateByteOrItemLimit(bool byteLimit)
    {
        var page = 0;
        using var http = CreateHttp(_ => Json($"{{\"assets\":{{\"items\":[{{\"id\":\"asset-{++page}\"}}],\"nextPage\":{page + 1}}}}}"));
        var limits = byteLimit ? new ImmichTransferLimits { MaxSearchBytes = 100 } : new ImmichTransferLimits { MaxSearchAssets = 1 };
        var result = await CreateClient(http, limits).GetUnassignedAssetsAsync(CancellationToken.None);
        Assert.False(result.IsSuccess);
        Assert.Empty(result.Assets);
        Assert.Equal(2, page);
    }

    private static ImmichAssetClient CreateClient(HttpClient http, ImmichTransferLimits? limits = null) =>
        new(http, new RetrySettings { MaxAttempts = 1 }, NullLogger<ImmichAssetClient>.Instance, limits ?? new());

    private static HttpClient CreateHttp(Func<HttpRequestMessage, HttpResponseMessage> respond) =>
        new(new TestHandler(respond)) { BaseAddress = new Uri("https://immich.example.test/api/") };

    private static HttpResponseMessage Bytes(byte[] bytes) => new(HttpStatusCode.OK) { Content = new ByteArrayContent(bytes) };
    private static HttpResponseMessage Json(string json) => new(HttpStatusCode.OK) { Content = new StringContent(json, Encoding.UTF8, "application/json") };
    private static HttpResponseMessage StreamResponse(Stream stream, long? length = null, HttpStatusCode status = HttpStatusCode.OK)
    {
        var content = new StreamContent(stream);
        if (length.HasValue) content.Headers.ContentLength = length;
        return new HttpResponseMessage(status) { Content = content };
    }

    private sealed class TestHandler(Func<HttpRequestMessage, HttpResponseMessage> respond) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => Task.FromResult(respond(request));
    }

    private sealed class TestDirectory : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"ifw-transfer-{Guid.NewGuid():N}");
        public TestDirectory() => Directory.CreateDirectory(Path);
        public void Dispose() => Directory.Delete(Path, recursive: true);
    }

    private class GeneratedStream(long length, Action? onRead = null) : Stream
    {
        public long BytesRead { get; private set; }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => BytesRead; set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count)
        {
            onRead?.Invoke();
            var read = (int)Math.Min(length - BytesRead, count);
            Array.Fill(buffer, (byte)'x', offset, read);
            BytesRead += read;
            return read;
        }
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            onRead?.Invoke();
            cancellationToken.ThrowIfCancellationRequested();
            var count = (int)Math.Min(length - BytesRead, buffer.Length);
            buffer.Span[..count].Fill((byte)'x');
            BytesRead += count;
            return ValueTask.FromResult(count);
        }
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

    private sealed class StallingStream() : GeneratedStream(0)
    {
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            return 0;
        }
    }
}
