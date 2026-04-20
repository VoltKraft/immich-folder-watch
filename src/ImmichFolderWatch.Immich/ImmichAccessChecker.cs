using System.Net;
using System.Text;
using System.Text.Json;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Immich;

public sealed class ImmichAccessChecker
{
    private const string InvalidId = "not-a-valid-id";

    private readonly HttpClient _httpClient;

    public ImmichAccessChecker(HttpClient httpClient)
    {
        _httpClient = httpClient;
    }

    public Task<ImmichAccessCheckResult> CheckAsync(bool requireAlbumPermissions, CancellationToken cancellationToken)
    {
        return CheckAsync(requireAlbumPermissions, requireDownloadPermissions: false, cancellationToken);
    }

    public async Task<ImmichAccessCheckResult> CheckAsync(bool requireAlbumPermissions, bool requireDownloadPermissions, CancellationToken cancellationToken)
    {
        var urlProbe = await ProbeUrlAsync(cancellationToken);
        if (urlProbe.Decision != ProbeDecision.Passed)
        {
            return new ImmichAccessCheckResult
            {
                UrlState = CheckState.Failed,
                UrlMessage = urlProbe.Message,
                ApiKeyState = CheckState.NotChecked,
                ApiKeyMessage = "Not checked because the URL could not be verified.",
                PermissionsState = CheckState.NotChecked,
                PermissionsMessage = "Not checked because the URL could not be verified.",
                PermissionResults = CreateNotCheckedPermissionResults("Not checked because the URL could not be verified.", requireAlbumPermissions, requireDownloadPermissions),
            };
        }

        var apiKeyProbe = await ProbeApiKeyAsync(cancellationToken);
        if (apiKeyProbe.Decision != ProbeDecision.Passed)
        {
            return new ImmichAccessCheckResult
            {
                UrlState = CheckState.Passed,
                UrlMessage = urlProbe.Message,
                ApiKeyState = CheckState.Failed,
                ApiKeyMessage = apiKeyProbe.Message,
                PermissionsState = CheckState.NotChecked,
                PermissionsMessage = "Not checked because the API key was not accepted.",
                PermissionResults = CreateNotCheckedPermissionResults("Not checked because the API key was not accepted.", requireAlbumPermissions, requireDownloadPermissions),
            };
        }

        var permissionResults = new[]
        {
            CreateUploadPermissionResult(await ProbeAssetUploadPermissionAsync(cancellationToken)),
            CreateAlbumReadPermissionResult(await ProbeAlbumReadPermissionAsync(cancellationToken), requireAlbumPermissions),
            CreateAlbumCreatePermissionResult(await ProbeAlbumCreatePermissionAsync(cancellationToken), requireAlbumPermissions),
            CreateAlbumAssetCreatePermissionResult(await ProbeAlbumAssetCreatePermissionAsync(cancellationToken), requireAlbumPermissions),
            CreateAssetDownloadPermissionResult(await ProbeAssetDownloadPermissionAsync(cancellationToken), requireDownloadPermissions),
        };

        return new ImmichAccessCheckResult
        {
            UrlState = CheckState.Passed,
            UrlMessage = urlProbe.Message,
            ApiKeyState = CheckState.Passed,
            ApiKeyMessage = apiKeyProbe.Message,
            PermissionsState = DeterminePermissionsOverallState(permissionResults, requireAlbumPermissions || requireDownloadPermissions),
            PermissionsMessage = DeterminePermissionsOverallMessage(permissionResults, requireAlbumPermissions || requireDownloadPermissions),
            PermissionResults = permissionResults,
        };
    }

    private async Task<ProbeResult> ProbeUrlAsync(CancellationToken cancellationToken)
    {
        var routes = new[]
        {
            ImmichApiRoutes.ServerPing,
            ImmichApiRoutes.ServerInfoPing,
            ImmichApiRoutes.ServerInfo,
        };

        ProbeResult? lastFailure = null;
        foreach (var route in routes)
        {
            var result = await SendAsync(() => CreateGetRequest(route), cancellationToken);
            if (!result.IsHttpResponse)
            {
                lastFailure = new ProbeResult(ProbeDecision.Failed, $"URL check failed for '{route}': {result.Message}");
                continue;
            }

            if (result.StatusCode is HttpStatusCode.OK or HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
            {
                return new ProbeResult(ProbeDecision.Passed, $"Immich URL reached successfully via '{route}'.");
            }

            if (result.StatusCode == HttpStatusCode.NotFound)
            {
                lastFailure = new ProbeResult(ProbeDecision.Warning, $"Endpoint '{route}' was not found.");
                continue;
            }

            return new ProbeResult(
                ProbeDecision.Failed,
                $"URL check failed on '{route}' with HTTP {(int)result.StatusCode}: {result.Message}");
        }

        return lastFailure is not null
            ? new ProbeResult(ProbeDecision.Failed, $"URL check failed. {lastFailure.Value.Message}")
            : new ProbeResult(ProbeDecision.Failed, "URL check failed. No Immich endpoint responded.");
    }

    private async Task<ProbeResult> ProbeApiKeyAsync(CancellationToken cancellationToken)
    {
        var albumReadProbe = await ProbeAlbumReadPermissionAsync(cancellationToken);
        if (albumReadProbe.Decision == ProbeDecision.Passed || albumReadProbe.Decision == ProbeDecision.Forbidden)
        {
            return new ProbeResult(ProbeDecision.Passed, "API key accepted by Immich.");
        }

        if (albumReadProbe.Decision == ProbeDecision.Unauthorized)
        {
            return new ProbeResult(ProbeDecision.Failed, albumReadProbe.Message);
        }

        var uploadProbe = await ProbeAssetUploadPermissionAsync(cancellationToken);
        return uploadProbe.Decision switch
        {
            ProbeDecision.Passed or ProbeDecision.Forbidden => new ProbeResult(ProbeDecision.Passed, "API key accepted by Immich."),
            ProbeDecision.Unauthorized => new ProbeResult(ProbeDecision.Failed, uploadProbe.Message),
            _ => new ProbeResult(ProbeDecision.Failed, "API key could not be validated against the current Immich API endpoints."),
        };
    }

    private async Task<ProbeResult> ProbeAssetUploadPermissionAsync(CancellationToken cancellationToken)
    {
        var probe = await SendAsync(
            () =>
            {
                var request = CreateRequest(HttpMethod.Post, ImmichApiRoutes.AssetUpload);
                request.Content = new MultipartFormDataContent();
                return request;
            },
            cancellationToken);

        return InterpretPermissionProbe(
            probe,
            "Upload assets",
            routeUnavailableIsWarning: false,
            successStatusCodes: [HttpStatusCode.OK, HttpStatusCode.Created, HttpStatusCode.Accepted, HttpStatusCode.NoContent, HttpStatusCode.BadRequest, HttpStatusCode.Conflict, HttpStatusCode.UnsupportedMediaType, HttpStatusCode.UnprocessableEntity]);
    }

    private async Task<ProbeResult> ProbeAlbumReadPermissionAsync(CancellationToken cancellationToken)
    {
        var probe = await SendAsync(() => CreateGetRequest(ImmichApiRoutes.Albums), cancellationToken);
        return InterpretPermissionProbe(
            probe,
            "Read albums",
            routeUnavailableIsWarning: true,
            successStatusCodes: [HttpStatusCode.OK, HttpStatusCode.NoContent]);
    }

    private async Task<ProbeResult> ProbeAlbumCreatePermissionAsync(CancellationToken cancellationToken)
    {
        var probe = await SendAsync(
            () =>
            {
                var request = CreateRequest(HttpMethod.Post, ImmichApiRoutes.Albums);
                request.Content = CreateJsonContent(new { });
                return request;
            },
            cancellationToken);

        return InterpretPermissionProbe(
            probe,
            "Create albums",
            routeUnavailableIsWarning: true,
            successStatusCodes: [HttpStatusCode.OK, HttpStatusCode.Created, HttpStatusCode.BadRequest, HttpStatusCode.Conflict, HttpStatusCode.UnprocessableEntity]);
    }

    private async Task<ProbeResult> ProbeAssetDownloadPermissionAsync(CancellationToken cancellationToken)
    {
        var probe = await SendAsync(() => CreateGetRequest(ImmichApiRoutes.AssetOriginalFile(InvalidId)), cancellationToken);
        return InterpretPermissionProbe(
            probe,
            "Download assets",
            routeUnavailableIsWarning: true,
            successStatusCodes: [HttpStatusCode.OK, HttpStatusCode.NoContent, HttpStatusCode.BadRequest, HttpStatusCode.NotFound, HttpStatusCode.UnprocessableEntity]);
    }

    private async Task<ProbeResult> ProbeAlbumAssetCreatePermissionAsync(CancellationToken cancellationToken)
    {
        var candidates = new[]
        {
            new ProbeCandidate(HttpMethod.Put, ImmichApiRoutes.AlbumAssets(InvalidId), "{\"ids\":[\"not-a-valid-id\"]}"),
            new ProbeCandidate(HttpMethod.Post, ImmichApiRoutes.AlbumAssets(InvalidId), "{\"ids\":[\"not-a-valid-id\"]}"),
            new ProbeCandidate(HttpMethod.Put, ImmichApiRoutes.AlbumsAssets, "{\"albumId\":\"not-a-valid-id\",\"ids\":[\"not-a-valid-id\"]}"),
            new ProbeCandidate(HttpMethod.Post, ImmichApiRoutes.AlbumsAssets, "{\"albumId\":\"not-a-valid-id\",\"ids\":[\"not-a-valid-id\"]}"),
        };

        ProbeResult? lastWarning = null;
        foreach (var candidate in candidates)
        {
            var probe = await SendAsync(
                () =>
                {
                    var request = CreateRequest(candidate.Method, candidate.Route);
                    request.Content = CreateJsonContent(candidate.JsonPayload);
                    return request;
                },
                cancellationToken);

            var result = InterpretPermissionProbe(
                probe,
                "Add assets to albums",
                routeUnavailableIsWarning: true,
                successStatusCodes: [HttpStatusCode.OK, HttpStatusCode.Created, HttpStatusCode.Accepted, HttpStatusCode.NoContent, HttpStatusCode.BadRequest, HttpStatusCode.Conflict, HttpStatusCode.UnsupportedMediaType, HttpStatusCode.UnprocessableEntity]);

            if (result.Decision == ProbeDecision.Warning)
            {
                lastWarning = result;
                continue;
            }

            return result;
        }

        return lastWarning ?? new ProbeResult(ProbeDecision.Warning, "The album asset endpoint could not be verified against the current Immich API shape.");
    }

    private static CheckState DeterminePermissionsOverallState(IReadOnlyList<ImmichPermissionCheckResult> permissionResults, bool requireAlbumPermissions)
    {
        if (permissionResults.Any(result => result.BlocksConfigVerification && result.State == CheckState.Failed))
        {
            return CheckState.Failed;
        }

        if (requireAlbumPermissions && permissionResults.Any(result => result.State is CheckState.Warning or CheckState.Failed))
        {
            return CheckState.Warning;
        }

        return CheckState.Passed;
    }

    private static string DeterminePermissionsOverallMessage(IReadOnlyList<ImmichPermissionCheckResult> permissionResults, bool requireAlbumPermissions)
    {
        if (permissionResults.All(result => result.State == CheckState.Passed))
        {
            return requireAlbumPermissions
                ? "All required Immich permissions for uploads and album placement are available."
                : "All required Immich permissions for uploads are available.";
        }

        if (permissionResults.Any(result => result.BlocksConfigVerification && result.State == CheckState.Failed))
        {
            return requireAlbumPermissions
                ? "A permission required for uploads or album placement is missing."
                : "A permission required for uploads is missing.";
        }

        return "Album-related permissions are optional until a source uses an album name.";
    }

    private static IReadOnlyList<ImmichPermissionCheckResult> CreateNotCheckedPermissionResults(string message, bool requireAlbumPermissions, bool requireDownloadPermissions)
    {
        return new[]
        {
            new ImmichPermissionCheckResult
            {
                PermissionName = "asset.upload",
                DisplayName = "Asset Upload",
                State = CheckState.NotChecked,
                Message = message,
                BlocksConfigVerification = true,
            },
            new ImmichPermissionCheckResult
            {
                PermissionName = "album.read",
                DisplayName = "Album Read",
                State = CheckState.NotChecked,
                Message = message,
                BlocksConfigVerification = requireAlbumPermissions,
            },
            new ImmichPermissionCheckResult
            {
                PermissionName = "album.create",
                DisplayName = "Album Create",
                State = CheckState.NotChecked,
                Message = message,
                BlocksConfigVerification = requireAlbumPermissions,
            },
            new ImmichPermissionCheckResult
            {
                PermissionName = "albumAsset.create",
                DisplayName = "Add Asset To Album",
                State = CheckState.NotChecked,
                Message = message,
                BlocksConfigVerification = requireAlbumPermissions,
            },
            new ImmichPermissionCheckResult
            {
                PermissionName = "asset.download",
                DisplayName = "Asset Download",
                State = CheckState.NotChecked,
                Message = message,
                BlocksConfigVerification = requireDownloadPermissions,
            },
        };
    }

    private static ImmichPermissionCheckResult CreateUploadPermissionResult(ProbeResult probe)
    {
        return CreatePermissionResult("asset.upload", "Asset Upload", blocksConfigVerification: true, probe);
    }

    private static ImmichPermissionCheckResult CreateAlbumReadPermissionResult(ProbeResult probe, bool blocksConfigVerification)
    {
        return CreatePermissionResult("album.read", "Album Read", blocksConfigVerification, probe);
    }

    private static ImmichPermissionCheckResult CreateAlbumCreatePermissionResult(ProbeResult probe, bool blocksConfigVerification)
    {
        return CreatePermissionResult("album.create", "Album Create", blocksConfigVerification, probe);
    }

    private static ImmichPermissionCheckResult CreateAlbumAssetCreatePermissionResult(ProbeResult probe, bool blocksConfigVerification)
    {
        return CreatePermissionResult("albumAsset.create", "Add Asset To Album", blocksConfigVerification, probe);
    }

    private static ImmichPermissionCheckResult CreateAssetDownloadPermissionResult(ProbeResult probe, bool blocksConfigVerification)
    {
        return CreatePermissionResult("asset.download", "Asset Download", blocksConfigVerification, probe);
    }

    private static ImmichPermissionCheckResult CreatePermissionResult(string permissionName, string displayName, bool blocksConfigVerification, ProbeResult probe)
    {
        return new ImmichPermissionCheckResult
        {
            PermissionName = permissionName,
            DisplayName = displayName,
            State = probe.Decision switch
            {
                ProbeDecision.Passed => CheckState.Passed,
                ProbeDecision.Warning => CheckState.Warning,
                _ => CheckState.Failed,
            },
            Message = probe.Message,
            BlocksConfigVerification = blocksConfigVerification,
        };
    }

    private static ProbeResult InterpretPermissionProbe(
        SendResult probe,
        string operationName,
        bool routeUnavailableIsWarning,
        HttpStatusCode[] successStatusCodes)
    {
        if (!probe.IsHttpResponse)
        {
            return new ProbeResult(ProbeDecision.Failed, $"{operationName} check failed: {probe.Message}");
        }

        if (successStatusCodes.Contains(probe.StatusCode))
        {
            return new ProbeResult(ProbeDecision.Passed, $"{operationName} is permitted.");
        }

        return probe.StatusCode switch
        {
            HttpStatusCode.Unauthorized => new ProbeResult(ProbeDecision.Unauthorized, "Immich rejected the API key."),
            HttpStatusCode.Forbidden => new ProbeResult(ProbeDecision.Forbidden, $"{operationName} is not permitted for this API key."),
            HttpStatusCode.NotFound or HttpStatusCode.MethodNotAllowed when routeUnavailableIsWarning => new ProbeResult(ProbeDecision.Warning, $"{operationName} could not be verified because the current Immich endpoint shape did not match the probe."),
            HttpStatusCode.NotFound or HttpStatusCode.MethodNotAllowed => new ProbeResult(ProbeDecision.Failed, $"{operationName} could not be verified because the expected endpoint was not available."),
            _ => new ProbeResult(ProbeDecision.Failed, $"{operationName} check failed with HTTP {(int)probe.StatusCode}: {probe.Message}"),
        };
    }

    private static HttpRequestMessage CreateGetRequest(string route)
    {
        return CreateRequest(HttpMethod.Get, route);
    }

    private static HttpRequestMessage CreateRequest(HttpMethod method, string route)
    {
        return new HttpRequestMessage(method, route);
    }

    private static StringContent CreateJsonContent<T>(T payload)
    {
        return new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
    }

    private static StringContent CreateJsonContent(string payload)
    {
        return new StringContent(payload, Encoding.UTF8, "application/json");
    }

    private async Task<SendResult> SendAsync(Func<HttpRequestMessage> requestFactory, CancellationToken cancellationToken)
    {
        try
        {
            using var request = requestFactory();
            using var response = await _httpClient.SendAsync(request, cancellationToken);
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            return new SendResult(response.StatusCode, TrimMessage(body));
        }
        catch (Exception ex)
        {
            return new SendResult(ex.Message);
        }
    }

    private static string TrimMessage(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "No response body was returned.";
        }

        return value.Length <= 256 ? value : value[..256];
    }

    private readonly record struct ProbeCandidate(HttpMethod Method, string Route, string JsonPayload);

    private readonly record struct SendResult(HttpStatusCode StatusCode, string Message)
    {
        public SendResult(string message)
            : this(0, message)
        {
            IsHttpResponse = false;
        }

        public bool IsHttpResponse { get; init; } = true;
    }

    private readonly record struct ProbeResult(ProbeDecision Decision, string Message);

    private enum ProbeDecision
    {
        Passed = 0,
        Unauthorized = 1,
        Forbidden = 2,
        Warning = 3,
        Failed = 4,
    }
}
