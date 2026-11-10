using System.Net;
using System.Text;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class HandleBoundTransferTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task UploadRetriesUseOriginalFileAfterLeafReplacement(bool legacyFallback)
    {
        using var directory = new TransferDirectory();
        var file = Path.Combine(directory.Path, "photo.jpg");
        await File.WriteAllTextAsync(file, "authorized-original");
        var bodies = new List<string>();
        using var http = new HttpClient(new AsyncHandler(async request =>
        {
            bodies.Add(await request.Content!.ReadAsStringAsync());
            if (bodies.Count == 1)
            {
                File.Move(file, file + ".old");
                await File.WriteAllTextAsync(file, "replacement-private");
                return new HttpResponseMessage(legacyFallback ? HttpStatusCode.BadRequest : HttpStatusCode.ServiceUnavailable)
                {
                    Content = new StringContent(legacyFallback ? "deviceAssetId must be a string" : "try again"),
                };
            }
            return Json("{\"id\":\"asset\"}");
        })) { BaseAddress = new Uri("https://immich.example.test/api/") };
        var client = new ImmichAssetClient(http, new RetrySettings { MaxAttempts = 2, BaseDelayMilliseconds = 1 }, NullLogger<ImmichAssetClient>.Instance);
        var result = await client.UploadAssetAsync(new UploadAssetRequest(file, "", directory.Path), default);
        Assert.True(result.IsSuccess, result.ErrorMessage);
        Assert.Equal(2, bodies.Count);
        Assert.All(bodies, body =>
        {
            Assert.Contains("authorized-original", body);
            Assert.DoesNotContain("replacement-private", body);
        });
        Assert.Equal("replacement-private", await File.ReadAllTextAsync(file));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DownloadPublicationAndCleanupStayInPinnedParent(bool failTransfer)
    {
        using var directory = new TransferDirectory();
        var watch = Directory.CreateDirectory(Path.Combine(directory.Path, "watch")).FullName;
        var moved = Path.Combine(directory.Path, "moved");
        var outside = Directory.CreateDirectory(Path.Combine(directory.Path, "outside")).FullName;
        await File.WriteAllTextAsync(Path.Combine(outside, "sentinel.jpg"), "private");
        using var root = SecureWatchRoot.Open(watch);
        var renamed = false;
        using (var lease = root.CreateDownload("photo.jpg"))
        {
            using var http = new HttpClient(new AsyncHandler(_ =>
            {
                try { Directory.Move(watch, moved); renamed = true; }
                catch (IOException) when (OperatingSystem.IsWindows()) { }
                if (renamed) Directory.CreateSymbolicLink(watch, outside);
                return Task.FromResult(new HttpResponseMessage(failTransfer ? HttpStatusCode.ServiceUnavailable : HttpStatusCode.OK)
                { Content = new StringContent("downloaded") });
            })) { BaseAddress = new Uri("https://immich.example.test/api/") };
            var client = new ImmichAssetClient(http, new RetrySettings { MaxAttempts = 1 }, NullLogger<ImmichAssetClient>.Instance);
            var result = await client.DownloadAssetAsync("asset", lease, default);
            Assert.Equal(!failTransfer, result.IsSuccess);
            if (result.IsSuccess)
            {
                lease.SetTimestamps(new DateTime(2020, 1, 2, 0, 0, 0, DateTimeKind.Utc), new DateTime(2021, 1, 2, 0, 0, 0, DateTimeKind.Utc));
                lease.CompleteNoReplace();
                Assert.Equal(10, lease.Length);
            }
        }
        Assert.Equal("private", await File.ReadAllTextAsync(Path.Combine(outside, "sentinel.jpg")));
        Assert.False(File.Exists(Path.Combine(outside, "photo.jpg")));
        var authorized = renamed ? moved : watch;
        Assert.Equal(!failTransfer, File.Exists(Path.Combine(authorized, "photo.jpg")));
        Assert.Empty(Directory.EnumerateFiles(authorized, "payload", SearchOption.AllDirectories));
        if (renamed) Directory.Delete(watch);
    }

    [Fact]
    public async Task LegacyIdentifiersDistinguishEqualFingerprintReplacementContent()
    {
        using var directory = new TransferDirectory();
        var file = Path.Combine(directory.Path, "photo.jpg");
        await File.WriteAllTextAsync(file, "original");
        var modified = File.GetLastWriteTimeUtc(file);
        var identifiers = new List<string>();
        var contents = new List<string>();
        using var http = new HttpClient(new AsyncHandler(async request =>
        {
            var parts = (MultipartFormDataContent)request.Content!;
            var id = parts.SingleOrDefault(part => part.Headers.ContentDisposition?.Name?.Trim('"') == "deviceAssetId");
            if (id is null)
                return new HttpResponseMessage(HttpStatusCode.BadRequest) { Content = new StringContent("deviceAssetId must be a string") };
            identifiers.Add(await id.ReadAsStringAsync());
            contents.Add(await parts.Single(part => part.Headers.ContentDisposition?.Name?.Trim('"') == "assetData").ReadAsStringAsync());
            return Json("{\"id\":\"asset\"}");
        })) { BaseAddress = new Uri("https://immich.example.test/api/") };
        var client = new ImmichAssetClient(http, new RetrySettings { MaxAttempts = 1 }, NullLogger<ImmichAssetClient>.Instance);
        Assert.True((await client.UploadAssetAsync(new UploadAssetRequest(file, "", directory.Path), default)).IsSuccess);
        File.Move(file, file + ".old");
        await File.WriteAllTextAsync(file, "replaced");
        File.SetLastWriteTimeUtc(file, modified);
        Assert.True((await client.UploadAssetAsync(new UploadAssetRequest(file, "", directory.Path), default)).IsSuccess);
        Assert.NotEqual(identifiers[0], identifiers[1]);
        Assert.Equal(new[] { "original", "replaced" }, contents);
    }

    private static HttpResponseMessage Json(string body) => new(HttpStatusCode.OK) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
    private sealed class AsyncHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> respond) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => respond(request);
    }
    private sealed class TransferDirectory : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "ifw-bound-" + Guid.NewGuid().ToString("N"));
        public TransferDirectory() => Directory.CreateDirectory(Path);
        public void Dispose() => Directory.Delete(Path, recursive: true);
    }
}
