using System.Net;
using System.Text;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class AlbumOwnershipSecurityTests
{
    [Fact]
    public async Task OwnershipSurvivesRestartAndIsScopedByAccountAndRoot()
    {
        var dir = Directory.CreateTempSubdirectory("ifw-ownership-");
        try
        {
            var db = Path.Combine(dir.FullName, "state.db");
            var store = new SqliteSyncStateStore(db);
            await store.SaveOwnedAlbumAsync("account", dir.FullName, "Photos", "owned-id", default);
            store = new SqliteSyncStateStore(db);
            Assert.Equal("owned-id", await store.GetOwnedAlbumAsync("account", dir.FullName, "Photos", default));
            Assert.Null(await store.GetOwnedAlbumAsync("other", dir.FullName, "Photos", default));
            Assert.Null(await store.GetOwnedAlbumAsync("account", dir.FullName + "-other", "Photos", default));
            await store.RemoveOwnedAlbumAsync("account", dir.FullName, "Photos", "stale-id", default);
            Assert.Equal("owned-id", await store.GetOwnedAlbumAsync("account", dir.FullName, "Photos", default));
            await store.MoveOwnedAlbumAsync("account", dir.FullName, "Photos", "Renamed", "owned-id", default);
            Assert.Null(await store.GetOwnedAlbumAsync("account", dir.FullName, "Photos", default));
            Assert.Equal("owned-id", await store.GetOwnedAlbumAsync("account", dir.FullName, "Renamed", default));
            await Assert.ThrowsAnyAsync<Exception>(() => store.SaveOwnedAlbumAsync("account", dir.FullName, "Renamed", "replacement", default));
            await Assert.ThrowsAsync<ArgumentException>(() => store.GetOwnedAlbumAsync("account", dir.FullName, "../escape", default));
        }
        finally
        {
            // Disposed store connections remain pooled; Windows keeps their files
            // locked until the pool is cleared, as in the other database fixtures.
            Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
            dir.Delete(true);
        }
    }

    [Fact]
    public async Task CreateOwnedAlbum_DoesNotAdoptExistingAlbum()
    {
        using var handler = new Handler(_ => Json("[{\"id\":\"existing\",\"albumName\":\"Photos\"}]"));
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://example.invalid/api/") };
        var client = new ImmichAssetClient(http, new RetrySettings(), NullLogger<ImmichAssetClient>.Instance);
        var result = await client.CreateOwnedAlbumAsync("Photos", default);
        Assert.False(result.IsSuccess);
        Assert.Equal(HttpStatusCode.Conflict, result.StatusCode);
        Assert.Equal(new[] { "GET /api/albums" }, handler.Requests);
    }

    [Fact]
    public async Task AmbiguousCreationResponseDoesNotRecoverOwnershipByName()
    {
        using var handler = new Handler(request => Json(request.Method == HttpMethod.Get ? "[]" : "{}"));
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://example.invalid/api/") };
        var client = new ImmichAssetClient(http, new RetrySettings(), NullLogger<ImmichAssetClient>.Instance);
        Assert.False((await client.CreateOwnedAlbumAsync("Photos", default)).IsSuccess);
        Assert.Equal(2, handler.Requests.Count);
    }

    [Fact]
    public async Task RenameAndDeleteUsePersistedIdEvenWhenAnotherAlbumHasTheOldName()
    {
        using var handler = new Handler(request => Json(request.Method == HttpMethod.Get
            ? "[{\"id\":\"owned\",\"albumName\":\"Changed remotely\"},{\"id\":\"unowned\",\"albumName\":\"Photos\"}]"
            : "{}"));
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://example.invalid/api/") };
        var client = new ImmichAssetClient(http, new RetrySettings(), NullLogger<ImmichAssetClient>.Instance);
        Assert.True((await client.RenameAlbumByIdAsync("owned", "New", default)).IsSuccess);
        Assert.True((await client.DeleteAlbumByIdAsync("owned", default)).IsSuccess);
        Assert.Equal(new[] { "GET /api/albums", "PATCH /api/albums/owned", "DELETE /api/albums/owned" }, handler.Requests);
    }

    [Fact]
    public async Task StaleOwnedIdDoesNotRenameReplacementWithTheSameName()
    {
        using var handler = new Handler(_ => Json("[{\"id\":\"replacement\",\"albumName\":\"Photos\"}]"));
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://example.invalid/api/") };
        var client = new ImmichAssetClient(http, new RetrySettings(), NullLogger<ImmichAssetClient>.Instance);
        Assert.True((await client.RenameAlbumByIdAsync("stale", "New", default)).AlbumMissing);
        Assert.Single(handler.Requests);
    }

    [Theory]
    [InlineData("existing", "Photos")]
    [InlineData("new-id", "Wrong name")]
    [InlineData("../existing", "Photos")]
    public async Task CreationResponseCannotAdoptKnownIdsOrUnexpectedIdentity(string id, string name)
    {
        using var handler = new Handler(request => Json(request.Method == HttpMethod.Get
            ? "[{\"id\":\"existing\",\"albumName\":\"Other\"}]"
            : System.Text.Json.JsonSerializer.Serialize(new { id, albumName = name })));
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://example.invalid/api/") };
        var client = new ImmichAssetClient(http, new RetrySettings(), NullLogger<ImmichAssetClient>.Instance);
        Assert.False((await client.CreateOwnedAlbumAsync("Photos", default)).IsSuccess);
    }

    private static HttpResponseMessage Json(string json) => new(HttpStatusCode.OK)
    {
        Content = new StringContent(json, Encoding.UTF8, "application/json"),
    };

    private sealed class Handler(Func<HttpRequestMessage, HttpResponseMessage> respond) : HttpMessageHandler
    {
        public List<string> Requests { get; } = [];
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests.Add($"{request.Method} {request.RequestUri!.AbsolutePath}");
            return Task.FromResult(respond(request));
        }
    }
}
