using System.Collections.Concurrent;
using System.Globalization;
using System.Net;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core;

/// <summary>
/// Executes the language-neutral RW-01 corpus against the shipping implementation.
/// Network calls end at an in-memory HTTP handler; files and databases are synthetic.
/// </summary>
public sealed class RustRewriteBehaviorContractTests
{
    private const string SyntheticApiKey = "synthetic-rw01-key";

    public static IEnumerable<object[]> NormalizationCases => ReadCases("normalization.json");
    public static IEnumerable<object[]> FilterCases => ReadCases("filters.json");
    public static IEnumerable<object[]> QueueCases => ReadCases("queue.json");
    public static IEnumerable<object[]> ReadinessCases => ReadCases("readiness.json");
    public static IEnumerable<object[]> TransportCases => ReadCases("transport.json");
    public static IEnumerable<object[]> HttpCases => ReadCases("http.json");
    public static IEnumerable<object[]> ApplyCases => ReadCases("apply.json");
    public static IEnumerable<object[]> WorkerCases => ReadCases("worker.json");
    public static IEnumerable<object[]> LegacyUploadCases => ReadCases("legacy-upload.json");

    [Theory]
    [MemberData(nameof(NormalizationCases))]
    public void Normalization_PreservesLegacyModeAndOrder(string id, string json)
    {
        using var document = ParseCase(id, json);
        var value = document.RootElement;
        Assert.Equal(String(value, "expectedMode"), WatchSourceSyncModes.Normalize(String(value, "mode")));
        Assert.Equal(String(value, "expectedOrder"), TransferOrders.Normalize(String(value, "order")));
    }

    [Theory]
    [MemberData(nameof(FilterCases))]
    public void Filters_ApplyExtensionAndGlobRulesWithinSource(string id, string json)
    {
        using var document = ParseCase(id, json);
        var value = document.RootElement;
        using var directory = new SyntheticDirectory();
        var source = Directory.CreateDirectory(Path.Combine(directory.Path, "media")).FullName;
        var filter = new WatchSourceFileFilter(source, Strings(value, "extensions"),
            Strings(value, "excludeDirectories"), Strings(value, "excludeFileNames"));

        Assert.Equal(value.GetProperty("expected").GetBoolean(),
            filter.IsMatch(Path.Combine(source, String(value, "path")!)));
    }

    [Theory]
    [MemberData(nameof(QueueCases))]
    public void Queue_OrdersAllPendingWorkBeforeTakingBoundedBatches(string id, string json)
    {
        using var document = ParseCase(id, json);
        var value = document.RootElement;
        using var directory = new SyntheticDirectory();
        var queue = new UploadBatchQueue();
        foreach (var item in value.GetProperty("items").EnumerateArray())
        {
            var path = Path.Combine(directory.Path, String(item, "name")!);
            if (String(item, "timestamp") is { } timestamp)
            {
                File.WriteAllText(path, "synthetic media");
                File.SetLastWriteTimeUtc(path, DateTimeOffset.Parse(timestamp, CultureInfo.InvariantCulture).UtcDateTime);
            }

            var request = new UploadAssetRequest(path, "Camera", directory.Path,
                Attempt: item.GetProperty("attempt").GetInt32());
            Assert.True(queue.TryEnqueue(request));
            Assert.False(queue.TryEnqueue(request));
        }

        var observed = new List<string>();
        while (queue.Count > 0)
        {
            var batch = queue.DequeueBatch(value.GetProperty("batchSize").GetInt32(), String(value, "order")!);
            Assert.InRange(batch.Count, 1, value.GetProperty("batchSize").GetInt32());
            observed.AddRange(batch.Select(item => Path.GetFileName(item.FilePath)));
        }

        Assert.Equal(Strings(value, "expected"), observed);
    }

    [Theory]
    [MemberData(nameof(ReadinessCases))]
    public async Task Readiness_UsesAuthorizedFileAndPropagatesCancellation(string id, string json)
    {
        using var document = ParseCase(id, json);
        var value = document.RootElement;
        using var directory = new SyntheticDirectory();
        if (value.GetProperty("exists").GetBoolean())
        {
            await File.WriteAllTextAsync(Path.Combine(directory.Path, "photo.jpg"), "synthetic media");
        }

        using var root = SecureWatchRoot.Open(directory.Path);
        using var cancellation = new CancellationTokenSource();
        if (value.GetProperty("cancelled").GetBoolean()) cancellation.Cancel();
        var timeout = TimeSpan.FromMilliseconds(value.GetProperty("timeoutMilliseconds").GetInt32());
        var checker = new FileReadinessChecker();
        switch (String(value, "expected"))
        {
            case "invalidTimeout":
                await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() =>
                    checker.WaitUntilReadyAsync(root, "photo.jpg", timeout, cancellation.Token));
                break;
            case "cancelled":
                await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
                    checker.WaitUntilReadyAsync(root, "photo.jpg", timeout, cancellation.Token));
                break;
            default:
                Assert.Equal(String(value, "expected") == "ready",
                    await checker.WaitUntilReadyAsync(root, "photo.jpg", timeout, cancellation.Token));
                break;
        }
    }

    [Theory]
    [MemberData(nameof(TransportCases))]
    public void Transport_RequiresExplicitHttpExceptionAndRejectsCredentialUrls(string id, string json)
    {
        using var document = ParseCase(id, json);
        var value = document.RootElement;
        Assert.Equal(value.GetProperty("accepted").GetBoolean(),
            AppConfigValidator.ValidateServerApiUrl(String(value, "url")!,
                value.GetProperty("allowInsecureHttp").GetBoolean()) is null);
    }

    [Theory]
    [MemberData(nameof(HttpCases))]
    public async Task Http_ProducesExpectedProtocolTraceAndCompleteResult(string id, string json)
    {
        using var document = ParseCase(id, json);
        var value = document.RootElement;
        using var handler = new ScriptedHttpHandler(value.GetProperty("steps"));
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://immich.example.test/api/") };
        http.DefaultRequestHeaders.Add("x-api-key", SyntheticApiKey);
        var limits = new ImmichTransferLimits();
        if (value.TryGetProperty("limits", out var configured))
        {
            if (configured.TryGetProperty("maxSearchAssets", out var assets)) limits = limits with { MaxSearchAssets = assets.GetInt32() };
            if (configured.TryGetProperty("maxMetadataBytes", out var bytes)) limits = limits with { MaxMetadataBytes = bytes.GetInt32() };
            if (configured.TryGetProperty("maxSearchPages", out var pages)) limits = limits with { MaxSearchPages = pages.GetInt32() };
        }

        var client = new ImmichAssetClient(http, new RetrySettings { MaxAttempts = 1 },
            NullLogger<ImmichAssetClient>.Instance, limits);
        switch (String(value, "operation"))
        {
            case "ping":
                if (value.GetProperty("success").GetBoolean()) await client.PingAsync(CancellationToken.None);
                else await Assert.ThrowsAsync<HttpRequestException>(() => client.PingAsync(CancellationToken.None));
                break;
            case "access":
                var access = await new ImmichAccessChecker(http).CheckAsync(true, true, CancellationToken.None);
                Assert.Equal(String(value, "urlState"), access.UrlState.ToString());
                Assert.Equal(String(value, "keyState"), access.ApiKeyState.ToString());
                Assert.Equal(String(value, "permissionsState"), access.PermissionsState.ToString());
                if (value.TryGetProperty("permissionNames", out _))
                {
                    Assert.Equal(Strings(value, "permissionNames"), access.PermissionResults.Select(permission => permission.PermissionName));
                    Assert.All(access.PermissionResults, permission =>
                    {
                        Assert.Equal(CheckState.Passed, permission.State);
                        Assert.True(permission.BlocksConfigVerification);
                    });
                }
                else Assert.All(access.PermissionResults, permission => Assert.Equal(CheckState.NotChecked, permission.State));
                break;
            case "albumAssets":
                var result = await client.GetAlbumAssetsAsync(String(value, "album")!, CancellationToken.None);
                Assert.Equal(value.GetProperty("success").GetBoolean(), result.IsSuccess);
                Assert.Equal(value.GetProperty("missing").GetBoolean(), result.AlbumMissing);
                Assert.Equal(Strings(value, "assetIds"), result.Assets.Select(asset => asset.Id));
                if (value.TryGetProperty("errorContains", out var error)) Assert.Contains(error.GetString()!, result.ErrorMessage);
                break;
            case "listAlbums":
                var albums = await client.ListAlbumsAsync(CancellationToken.None);
                Assert.Equal(value.GetProperty("success").GetBoolean(), albums.IsSuccess);
                Assert.Equal(Strings(value, "albumIds"), albums.Albums.Select(album => album.Id));
                if (value.TryGetProperty("errorContains", out var listError)) Assert.Contains(listError.GetString()!, albums.ErrorMessage);
                break;
            case "addAssets":
                var membership = await client.AddAssetsToAlbumAsync(String(value, "album")!, Strings(value, "inputAssetIds"), CancellationToken.None);
                Assert.Equal(value.GetProperty("success").GetBoolean(), membership.IsSuccess);
                break;
            case "unassigned":
                var unassigned = await client.GetUnassignedAssetsAsync(CancellationToken.None);
                Assert.Equal(value.GetProperty("success").GetBoolean(), unassigned.IsSuccess);
                Assert.Equal(Strings(value, "assetIds"), unassigned.Assets.Select(asset => asset.Id));
                break;
            case "trash":
                var trash = await client.TrashAssetsAsync(Strings(value, "inputAssetIds"), CancellationToken.None);
                Assert.Equal(value.GetProperty("success").GetBoolean(), trash.IsSuccess);
                break;
            case "deleteById":
                var deleted = await client.DeleteAlbumByIdAsync(String(value, "albumId")!, CancellationToken.None);
                Assert.Equal(value.GetProperty("success").GetBoolean(), deleted.IsSuccess);
                Assert.Equal(value.GetProperty("missing").GetBoolean(), deleted.AlbumMissing);
                break;
            case "renameById":
                var renamed = await client.RenameAlbumByIdAsync(String(value, "albumId")!, String(value, "newName")!, CancellationToken.None);
                Assert.Equal(value.GetProperty("success").GetBoolean(), renamed.IsSuccess);
                Assert.Equal(value.GetProperty("missing").GetBoolean(), renamed.AlbumMissing);
                Assert.Equal(String(value, "albumId"), renamed.AlbumId);
                break;
            case "createOwned":
                var created = await client.CreateOwnedAlbumAsync(String(value, "album")!, CancellationToken.None);
                Assert.Equal(value.GetProperty("success").GetBoolean(), created.IsSuccess);
                Assert.Equal(String(value, "albumId"), created.AlbumId);
                break;
            default:
                throw new InvalidOperationException("Unknown HTTP fixture operation.");
        }

        handler.AssertComplete();
    }

    [Theory]
    [MemberData(nameof(ApplyCases))]
    public async Task Apply_SeparatesDraftValidationPersistenceAndRestart(string id, string json)
    {
        using var document = ParseCase(id, json);
        var value = document.RootElement;
        using var directory = new SyntheticDirectory();
        Directory.CreateDirectory(Path.Combine(directory.Path, "media"));
        var path = Path.Combine(directory.Path, "config.yaml");
        await File.WriteAllTextAsync(path, "existing synthetic configuration");
        var config = CreateConfig(Path.Combine(directory.Path, "media"), WatchSourceSyncModes.UploadNew);
        config.Logging = new LoggingSettings { Target = LogTargets.File, LogDirectory = "logs" };
        var scenario = String(value, "scenario");
        if (scenario == "invalidLocal") config.Watch.MaxBatchSize = 0;
        var accessCalls = 0;
        var restartCalls = 0;
        var events = new List<string>();
        using var cancellation = new CancellationTokenSource();
        var service = new ConfigApplyService((_, _, _) =>
        {
            accessCalls++;
            events.Add("access");
            if (scenario == "cancelAfterAccess") cancellation.Cancel();
            return Task.FromResult(new ImmichAccessCheckResult
            {
                UrlState = CheckState.Passed,
                ApiKeyState = scenario == "accessRejected" ? CheckState.Failed : CheckState.Passed,
                ApiKeyMessage = "Synthetic API key rejected.",
                PermissionsState = CheckState.Passed,
            });
        });

        var success = false;
        var thrown = await Record.ExceptionAsync(async () =>
        {
            var result = await service.ApplyAsync(config, path, (applied, _) =>
            {
                restartCalls++;
                events.Add("restart");
                Assert.Equal(applied.Watch.Sources[0].Path, new AppConfigLoader().Load(path).Watch.Sources[0].Path);
                if (scenario == "restartFailed") throw new InvalidOperationException("Synthetic restart failure.");
                return Task.CompletedTask;
            }, _ => events.Add("checked"), () => events.Add("saving"), cancellation.Token);
            success = result.Success;
        });

        Assert.Equal(String(value, "exception"), thrown?.GetType().Name);
        Assert.Equal(value.GetProperty("success").GetBoolean(), success);
        Assert.Equal(value.GetProperty("accessCalls").GetInt32(), accessCalls);
        Assert.Equal(value.GetProperty("restartCalls").GetInt32(), restartCalls);
        Assert.Equal(Strings(value, "events"), events);
        Assert.Equal(value.GetProperty("saved").GetBoolean(),
            await File.ReadAllTextAsync(path) != "existing synthetic configuration");
    }

    [Theory]
    [MemberData(nameof(WorkerCases))]
    public async Task Worker_DistinguishesStartupFromCreatedFilesAndPersistsBeforeStop(string id, string json)
    {
        using var document = ParseCase(id, json);
        var value = document.RootElement;
        using var directory = new SyntheticDirectory();
        var media = Directory.CreateDirectory(Path.Combine(directory.Path, "media")).FullName;
        var existing = Path.Combine(media, "existing.jpg");
        await File.WriteAllTextAsync(existing, "synthetic existing media");
        var config = CreateConfig(media, String(value, "mode")!);
        var databasePath = Path.Combine(directory.Path, "sync-state.db");
        var store = new SqliteSyncStateStore(databasePath);
        var client = new SyntheticAssetClient();
        var status = new SyncStatusProvider();
        var logger = new ReconciliationLogger();
        using var worker = new FolderWatchWorker(config, new FileReadinessChecker(),
            new LocalFileDeletionService(), new UploadBatchQueue(), client, store, status, logger);
        await worker.StartAsync(CancellationToken.None);
        try
        {
            await logger.Ready.WaitAsync(TimeSpan.FromSeconds(15));
            var existingCount = value.GetProperty("existingUploadCount").GetInt32();
            if (existingCount > 0)
            {
                await WaitUntilAsync(() => status.ProcessedFileCount == existingCount && status.CurrentBatchSize == 0);
            }
            Assert.Equal(existingCount, client.Uploaded.Count);
            await File.WriteAllTextAsync(Path.Combine(media, "created.jpg"), "synthetic created media");
            var expectedTotal = existingCount + value.GetProperty("createdUploadCount").GetInt32();
            await WaitUntilAsync(() => client.Uploaded.Count == expectedTotal
                && status.ProcessedFileCount == 1 && status.CurrentBatchSize == 0);
        }
        finally
        {
            await worker.StopAsync(CancellationToken.None);
        }

        Assert.Equal(value.GetProperty("existingPreserved").GetBoolean(), File.Exists(existing));
        Assert.Equal(value.GetProperty("createdPreserved").GetBoolean(), File.Exists(Path.Combine(media, "created.jpg")));
        var expected = value.GetProperty("existingUploadCount").GetInt32() == 0
            ? new[] { "created.jpg" } : new[] { "existing.jpg", "created.jpg" };
        Assert.Equal(expected, client.Uploaded.ToArray());
        var scope = SyncAccountScope.Create(config.Immich.ServerApiUrl, config.Immich.ApiKey);
        var entries = await store.GetSourceEntriesAsync(scope, media);
        Assert.All(expected, name => Assert.Contains(entries,
            entry => entry.RelativePath == name && entry.Status == SyncEntryStatus.Synchronized && entry.AssetId is not null));
        Assert.NotNull(await store.GetLastSuccessfulSyncAsync(scope));
    }

    [Theory]
    [MemberData(nameof(LegacyUploadCases))]
    public async Task LegacyUpload_HashesAndRetriesTheRetainedFileWithExactDotNetEncoding(string id, string json)
    {
        using var document = ParseCase(id, json);
        var value = document.RootElement;
        using var directory = new SyntheticDirectory();
        var path = Path.Combine(directory.Path, "photo.jpg");
        var bytes = Convert.FromBase64String(String(value, "contentBase64")!);
        if (value.TryGetProperty("contentRepeats", out var repeats))
        {
            bytes = Enumerable.Repeat(bytes, repeats.GetInt32()).SelectMany(block => block).ToArray();
        }
        await File.WriteAllBytesAsync(path, bytes);
        var timestamp = DateTimeOffset.Parse(String(value, "modifiedUtc")!, CultureInfo.InvariantCulture).UtcDateTime;
        File.SetLastWriteTimeUtc(path, timestamp);
        using var root = SecureWatchRoot.Open(directory.Path);
        using var file = root.OpenRead("photo.jpg");
        Assert.Equal(long.Parse(String(value, "modifiedDotNetTicks")!, CultureInfo.InvariantCulture), file.LastWriteTimeUtc.Ticks);
        using var handler = new LegacyUploadHandler(value, bytes, path, timestamp);
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://immich.example.test/api/") };
        var client = new ImmichAssetClient(http, new RetrySettings { MaxAttempts = 1 },
            NullLogger<ImmichAssetClient>.Instance);

        var result = await client.UploadAssetAttemptAsync(new UploadAssetRequest(String(value, "displayPath")!, "")
        {
            SourceRoot = root,
            OpenedFile = file,
        }, CancellationToken.None);

        Assert.True(result.IsSuccess, result.ErrorMessage);
        Assert.Equal("synthetic-asset", result.AssetId);
        Assert.Equal(2, handler.RequestCount);
        Assert.True(file.Stream.CanRead);
    }

    private static AppConfig CreateConfig(string source, string mode) => new()
    {
        Immich = new ImmichSettings { ServerApiUrl = "https://immich.example.test/api", ApiKey = SyntheticApiKey },
        Watch = new WatchSettings
        {
            BatchIntervalSeconds = 1,
            FileReadyTimeoutSeconds = 1,
            MaxBatchSize = 1,
            Sources = [new() { Path = source, AlbumName = "Camera", Extensions = [".jpg"], SyncMode = mode }],
        },
    };

    private static async Task WaitUntilAsync(Func<bool> condition)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        while (!condition()) await Task.Delay(25, timeout.Token);
    }

    private static JsonDocument ParseCase(string id, string json)
    {
        var document = JsonDocument.Parse(json);
        Assert.Equal(id, String(document.RootElement, "id"));
        return document;
    }

    private static IEnumerable<object[]> ReadCases(string filename, [CallerFilePath] string source = "")
    {
        var path = Path.Combine(LocateFixtureDirectory(source), filename);
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        Assert.Equal(1, document.RootElement.GetProperty("fixtureVersion").GetInt32());
        foreach (var value in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            yield return [String(value, "id")!, value.GetRawText()];
        }
    }

    private static string LocateFixtureDirectory(string source)
    {
        const string relative = "rust/tests/fixtures/behavior";
        if (Environment.GetEnvironmentVariable("IFW_COMPATIBILITY_REPOSITORY") is { Length: > 0 } repository)
        {
            var explicitPath = Path.Combine(Path.GetFullPath(repository), relative);
            if (!Directory.Exists(explicitPath)) throw new DirectoryNotFoundException("The explicitly selected compatibility corpus does not exist.");
            return explicitPath;
        }
        for (var current = new DirectoryInfo(AppContext.BaseDirectory); current is not null; current = current.Parent)
        {
            var candidate = Path.Combine(current.FullName, relative);
            if (Directory.Exists(candidate)) return candidate;
        }
        return Path.GetFullPath(Path.Combine(Path.GetDirectoryName(source)!, "../..", relative));
    }

    private static string? String(JsonElement value, string name) => value.GetProperty(name).GetString();

    private static string[] Strings(JsonElement value, string name) =>
        value.GetProperty(name).EnumerateArray().Select(item => item.GetString()!).ToArray();

    private sealed class ScriptedHttpHandler(JsonElement steps) : HttpMessageHandler
    {
        private readonly JsonElement[] _steps = steps.EnumerateArray().ToArray();
        private int _position;
        private readonly List<Exception> _requestFailures = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            try
            {
                return await VerifyRequestAsync(request, cancellationToken);
            }
            catch (Exception exception)
            {
                // Production converts some transport exceptions to failure results. A
                // negative fixture must not accidentally swallow a failed assertion.
                _requestFailures.Add(exception);
                throw;
            }
        }

        private async Task<HttpResponseMessage> VerifyRequestAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Assert.InRange(_position, 0, _steps.Length - 1);
            var step = _steps[_position++];
            Assert.Equal(String(step, "method"), request.Method.Method);
            Assert.Equal("https://immich.example.test" + String(step, "path"), request.RequestUri!.AbsoluteUri);
            Assert.Equal(SyntheticApiKey, Assert.Single(request.Headers.GetValues("x-api-key")));
            if (step.TryGetProperty("requestJson", out var expectedJson))
            {
                using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(cancellationToken));
                Assert.True(JsonElement.DeepEquals(expectedJson, body.RootElement), "JSON request differs from the compatibility fixture.");
            }
            return new HttpResponseMessage((HttpStatusCode)step.GetProperty("status").GetInt32())
            {
                Content = new StringContent(String(step, "body")!, Encoding.UTF8, "application/json"),
            };
        }

        public void AssertComplete()
        {
            Assert.Empty(_requestFailures);
            Assert.Equal(_steps.Length, _position);
        }
    }

    private sealed class ReconciliationLogger : ILogger<FolderWatchWorker>
    {
        private readonly TaskCompletionSource _ready = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _passes;
        public Task Ready => _ready.Task;
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel logLevel) => true;
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception,
            Func<TState, Exception?, string> formatter)
        {
            if (logLevel == LogLevel.Information
                && formatter(state, exception).StartsWith("Persistent reconciliation for ", StringComparison.Ordinal)
                && Interlocked.Increment(ref _passes) == 2) _ready.TrySetResult();
        }
    }

    private sealed class LegacyUploadHandler(JsonElement value, byte[] originalBytes, string path, DateTime timestamp) : HttpMessageHandler
    {
        public int RequestCount { get; private set; }
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            RequestCount++;
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://immich.example.test/api/assets", request.RequestUri!.AbsoluteUri);
            var multipart = Assert.IsType<MultipartFormDataContent>(request.Content);
            var parts = multipart.ToDictionary(part => part.Headers.ContentDisposition!.Name!.Trim('"'));
            Assert.Equal(originalBytes, await parts["assetData"].ReadAsByteArrayAsync(cancellationToken));
            Assert.Equal(timestamp.ToString("O", CultureInfo.InvariantCulture),
                await parts["fileModifiedAt"].ReadAsStringAsync(cancellationToken));
            if (RequestCount == 1)
            {
                Assert.False(parts.ContainsKey("deviceAssetId"));
                Assert.False(parts.ContainsKey("deviceId"));
                try
                {
                    File.Move(path, path + ".retained");
                    await File.WriteAllBytesAsync(path, Enumerable.Repeat((byte)'x', originalBytes.Length).ToArray(), cancellationToken);
                    File.SetLastWriteTimeUtc(path, timestamp);
                }
                catch (IOException) when (OperatingSystem.IsWindows())
                {
                    // Denying replacement while the file is pinned is also a valid security outcome.
                }
                return new HttpResponseMessage(HttpStatusCode.UnprocessableEntity)
                {
                    Content = new StringContent("{\"message\":[\"deviceAssetId must be a string\",\"deviceId must be a string\"]}"),
                };
            }
            Assert.Equal(2, RequestCount);
            Assert.Equal(String(value, "deviceAssetId"), await parts["deviceAssetId"].ReadAsStringAsync(cancellationToken));
            Assert.Equal("immich-folder-watch", await parts["deviceId"].ReadAsStringAsync(cancellationToken));
            return new HttpResponseMessage(HttpStatusCode.Created) { Content = new StringContent("{\"id\":\"synthetic-asset\"}") };
        }
    }

    private sealed class SyntheticAssetClient : IImmichAssetClient
    {
        public ConcurrentQueue<string> Uploaded { get; } = new();
        public Task PingAsync(CancellationToken cancellationToken) => Task.CompletedTask;
        public Task<UploadAssetResult> UploadAssetAsync(UploadAssetRequest request, CancellationToken cancellationToken)
        {
            var name = Path.GetFileName(request.FilePath);
            Uploaded.Enqueue(name);
            return Task.FromResult(UploadAssetResult.Success("synthetic-" + name));
        }
        public Task<AlbumAssetsResult> GetAlbumAssetsAsync(string albumName, CancellationToken cancellationToken) =>
            Task.FromResult(AlbumAssetsResult.Success(Uploaded.Select(name => new AlbumAssetSummary("synthetic-" + name, name)).ToArray()));
        public Task<DownloadAssetResult> DownloadAssetAsync(string assetId, string destinationPath, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("Unexpected download in an upload-mode fixture.");
        public Task<AlbumListResult> ListAlbumsAsync(CancellationToken cancellationToken) => Task.FromResult(AlbumListResult.Success([]));
        public Task<UnassignedAssetsResult> GetUnassignedAssetsAsync(CancellationToken cancellationToken) => Task.FromResult(UnassignedAssetsResult.Success([]));
        public Task<EnsureAlbumResult> EnsureAlbumAsync(string albumName, CancellationToken cancellationToken) => Task.FromResult(EnsureAlbumResult.Success("synthetic-album"));
        public Task<AlbumMembershipUpdateResult> AddAssetsToAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken) => Task.FromResult(AlbumMembershipUpdateResult.Success());
        public Task<AlbumMembershipUpdateResult> RemoveAssetsFromAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken) => throw new InvalidOperationException("Unexpected album mutation.");
        public Task<TrashAssetsResult> TrashAssetsAsync(IReadOnlyList<string> assetIds, CancellationToken cancellationToken) => throw new InvalidOperationException("Unexpected remote deletion.");
        public Task<DeleteAlbumResult> DeleteAlbumAsync(string albumName, CancellationToken cancellationToken) => throw new InvalidOperationException("Unexpected album deletion.");
        public Task<RenameAlbumResult> RenameAlbumAsync(string oldAlbumName, string newAlbumName, CancellationToken cancellationToken) => throw new InvalidOperationException("Unexpected album rename.");
    }

    private sealed class SyntheticDirectory : IDisposable
    {
        public string Path { get; } = Directory.CreateTempSubdirectory("ifw-rw01-behavior-").FullName;
        public void Dispose()
        {
            Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
            Directory.Delete(Path, recursive: true);
        }
    }
}
