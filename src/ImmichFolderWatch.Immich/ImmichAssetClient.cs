using System.Globalization;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Immich;

public sealed class ImmichAssetClient : IImmichAssetClient, IImmichConnectivityVerifier
{
    private const int MaxBackoffMilliseconds = 30_000;

    private static readonly string[] PingRoutes =
    {
        ImmichApiRoutes.ServerPing,
        ImmichApiRoutes.ServerInfoPing,
    };

    private readonly HttpClient _httpClient;

    private readonly RetrySettings _retrySettings;

    private readonly ILogger<ImmichAssetClient> _logger;

    public ImmichAssetClient(
        HttpClient httpClient,
        RetrySettings retrySettings,
        ILogger<ImmichAssetClient> logger)
    {
        _httpClient = httpClient;
        _retrySettings = retrySettings;
        _logger = logger;
    }

    public async Task PingAsync(CancellationToken cancellationToken)
    {
        foreach (var route in PingRoutes)
        {
            if (await TryPingRouteAsync(route, cancellationToken))
            {
                return;
            }
        }

        if (await TryLightweightFallbackAsync(cancellationToken))
        {
            return;
        }

        throw new HttpRequestException("Immich reachability check failed. No ping endpoint responded successfully.");
    }

    public async Task<AlbumAssetsResult> GetAlbumAssetsAsync(string albumName, CancellationToken cancellationToken)
    {
        var normalized = NormalizeAlbumName(albumName);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return AlbumAssetsResult.Missing();
        }

        var albumsResult = await GetAlbumsAsync(cancellationToken);
        if (!albumsResult.IsSuccess)
        {
            return AlbumAssetsResult.Failure(albumsResult.StatusCode, albumsResult.ErrorMessage);
        }

        var matches = FindExactAlbumMatches(albumsResult.Albums, normalized);
        if (matches.Count == 0)
        {
            return AlbumAssetsResult.Missing();
        }

        if (matches.Count > 1)
        {
            return AlbumAssetsResult.Failure(null, BuildDuplicateAlbumError(normalized));
        }

        var searchResult = await SearchAssetsAsync(
            page => new
            {
                albumIds = new[] { matches[0].Id },
                page,
                size = 250,
            },
            "The album asset search response could not be parsed.",
            cancellationToken);

        return searchResult.IsSuccess
            ? AlbumAssetsResult.Success(searchResult.Assets)
            : AlbumAssetsResult.Failure(searchResult.StatusCode, searchResult.ErrorMessage);
    }

    public async Task<DownloadAssetResult> DownloadAssetAsync(string assetId, string destinationPath, CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(assetId);
        ArgumentException.ThrowIfNullOrWhiteSpace(destinationPath);

        var directory = Path.GetDirectoryName(destinationPath);
        if (!string.IsNullOrWhiteSpace(directory))
        {
            Directory.CreateDirectory(directory);
        }

        var tempPath = destinationPath + ".downloading";
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, ImmichApiRoutes.AssetOriginalFile(assetId));
            using var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            if (!response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadAsStringAsync(cancellationToken);
                return DownloadAssetResult.Failure(
                    response.StatusCode,
                    $"HTTP {(int)response.StatusCode}: {TrimForLog(body)}");
            }

            await using (var inputStream = await response.Content.ReadAsStreamAsync(cancellationToken))
            await using (var outputStream = new FileStream(tempPath, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                await inputStream.CopyToAsync(outputStream, cancellationToken);
            }

            if (File.Exists(destinationPath))
            {
                File.Delete(destinationPath);
            }

            File.Move(tempPath, destinationPath);
            return DownloadAssetResult.Success();
        }
        catch (Exception ex)
        {
            if (File.Exists(tempPath))
            {
                try
                {
                    File.Delete(tempPath);
                }
                catch (Exception)
                {
                }
            }

            _logger.LogError(ex, "Asset download failed for {AssetId}.", assetId);
            return DownloadAssetResult.Failure(null, ex.Message);
        }
    }

    public async Task<AlbumListResult> ListAlbumsAsync(CancellationToken cancellationToken)
    {
        var albumsResult = await GetAlbumsAsync(cancellationToken);
        if (!albumsResult.IsSuccess)
        {
            return AlbumListResult.Failure(albumsResult.StatusCode, albumsResult.ErrorMessage);
        }

        var albums = albumsResult.Albums
            .Select(album => new AlbumInfo(album.Id, album.Name))
            .ToList();
        return AlbumListResult.Success(albums);
    }

    public async Task<UnassignedAssetsResult> GetUnassignedAssetsAsync(CancellationToken cancellationToken)
    {
        var searchResult = await SearchAssetsAsync(
            page => new
            {
                isNotInAlbum = true,
                page,
                size = 250,
            },
            "The unassigned asset response could not be parsed.",
            cancellationToken);

        return searchResult.IsSuccess
            ? UnassignedAssetsResult.Success(searchResult.Assets)
            : UnassignedAssetsResult.Failure(searchResult.StatusCode, searchResult.ErrorMessage);
    }

    public async Task<AlbumMembershipUpdateResult> AddAssetsToAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(assetIds);

        var normalized = NormalizeAlbumName(albumName);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return AlbumMembershipUpdateResult.Failure(null, "Album name is required to add assets.");
        }

        if (assetIds.Count == 0)
        {
            return AlbumMembershipUpdateResult.Success();
        }

        var resolution = await ResolveOrCreateAlbumAsync(normalized, cancellationToken);
        if (!resolution.IsSuccess)
        {
            return AlbumMembershipUpdateResult.Failure(
                resolution.StatusCode,
                resolution.ErrorMessage ?? $"Album '{normalized}' could not be resolved.");
        }

        var operation = await AddAssetsToAlbumByIdAsync(resolution.AlbumId!, assetIds, cancellationToken);
        return operation.IsSuccess
            ? AlbumMembershipUpdateResult.Success()
            : AlbumMembershipUpdateResult.Failure(operation.StatusCode, operation.ErrorMessage ?? "Adding assets to the album failed.");
    }

    public async Task<AlbumMembershipUpdateResult> RemoveAssetsFromAlbumAsync(string albumName, IReadOnlyList<string> assetIds, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(assetIds);

        var normalized = NormalizeAlbumName(albumName);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return AlbumMembershipUpdateResult.Failure(null, "Album name is required to remove assets.");
        }

        if (assetIds.Count == 0)
        {
            return AlbumMembershipUpdateResult.Success();
        }

        var albumsResult = await GetAlbumsAsync(cancellationToken);
        if (!albumsResult.IsSuccess)
        {
            return AlbumMembershipUpdateResult.Failure(albumsResult.StatusCode, albumsResult.ErrorMessage);
        }

        var matches = FindExactAlbumMatches(albumsResult.Albums, normalized);
        if (matches.Count == 0)
        {
            return AlbumMembershipUpdateResult.Success();
        }

        if (matches.Count > 1)
        {
            return AlbumMembershipUpdateResult.Failure(null, BuildDuplicateAlbumError(normalized));
        }

        var result = await SendJsonAsync(
            HttpMethod.Delete,
            ImmichApiRoutes.AlbumAssets(matches[0].Id),
            new
            {
                ids = assetIds,
            },
            cancellationToken);

        if (!result.HasHttpResponse)
        {
            return AlbumMembershipUpdateResult.Failure(null, result.ErrorMessage);
        }

        if (!result.IsSuccessStatusCode)
        {
            return AlbumMembershipUpdateResult.Failure(
                result.StatusCode,
                $"HTTP {(int)result.StatusCode!.Value}: {TrimForLog(result.Body)}");
        }

        return AlbumMembershipUpdateResult.Success();
    }

    public async Task<TrashAssetsResult> TrashAssetsAsync(IReadOnlyList<string> assetIds, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(assetIds);

        if (assetIds.Count == 0)
        {
            return TrashAssetsResult.Success();
        }

        var result = await SendJsonAsync(
            HttpMethod.Delete,
            ImmichApiRoutes.AssetsBulk,
            new
            {
                ids = assetIds,
                force = false,
            },
            cancellationToken);

        if (!result.HasHttpResponse)
        {
            return TrashAssetsResult.Failure(null, result.ErrorMessage);
        }

        if (!result.IsSuccessStatusCode)
        {
            return TrashAssetsResult.Failure(
                result.StatusCode,
                $"HTTP {(int)result.StatusCode!.Value}: {TrimForLog(result.Body)}");
        }

        return TrashAssetsResult.Success();
    }

    public async Task<EnsureAlbumResult> EnsureAlbumAsync(string albumName, CancellationToken cancellationToken)
    {
        var normalized = NormalizeAlbumName(albumName);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return EnsureAlbumResult.Failure(null, "Album name is required.");
        }

        var resolution = await ResolveOrCreateAlbumAsync(normalized, cancellationToken);
        if (!resolution.IsSuccess)
        {
            return EnsureAlbumResult.Failure(
                resolution.StatusCode,
                resolution.ErrorMessage ?? $"Album '{normalized}' could not be resolved.");
        }

        return EnsureAlbumResult.Success(resolution.AlbumId!);
    }

    public async Task<DeleteAlbumResult> DeleteAlbumAsync(string albumName, CancellationToken cancellationToken)
    {
        var normalized = NormalizeAlbumName(albumName);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return DeleteAlbumResult.Failure(null, "Album name is required.");
        }

        var albumsResult = await GetAlbumsAsync(cancellationToken);
        if (!albumsResult.IsSuccess)
        {
            return DeleteAlbumResult.Failure(albumsResult.StatusCode, albumsResult.ErrorMessage);
        }

        var matches = FindExactAlbumMatches(albumsResult.Albums, normalized);
        if (matches.Count == 0)
        {
            return DeleteAlbumResult.Missing();
        }

        if (matches.Count > 1)
        {
            return DeleteAlbumResult.Failure(null, BuildDuplicateAlbumError(normalized));
        }

        var result = await SendAsync(HttpMethod.Delete, ImmichApiRoutes.AlbumInfo(matches[0].Id), content: null, cancellationToken);
        if (!result.HasHttpResponse)
        {
            return DeleteAlbumResult.Failure(null, result.ErrorMessage);
        }

        if (result.StatusCode == HttpStatusCode.NotFound)
        {
            return DeleteAlbumResult.Missing();
        }

        if (!result.IsSuccessStatusCode)
        {
            return DeleteAlbumResult.Failure(
                result.StatusCode,
                $"HTTP {(int)result.StatusCode!.Value}: {TrimForLog(result.Body)}");
        }

        return DeleteAlbumResult.Success();
    }

    public async Task<RenameAlbumResult> RenameAlbumAsync(string oldAlbumName, string newAlbumName, CancellationToken cancellationToken)
    {
        var oldNormalized = NormalizeAlbumName(oldAlbumName);
        var newNormalized = NormalizeAlbumName(newAlbumName);

        if (string.IsNullOrWhiteSpace(oldNormalized) || string.IsNullOrWhiteSpace(newNormalized))
        {
            return RenameAlbumResult.Failure(null, "Both old and new album names are required.");
        }

        if (string.Equals(oldNormalized, newNormalized, StringComparison.Ordinal))
        {
            var current = await GetAlbumsAsync(cancellationToken);
            if (!current.IsSuccess)
            {
                return RenameAlbumResult.Failure(current.StatusCode, current.ErrorMessage);
            }

            var existing = FindExactAlbumMatches(current.Albums, newNormalized);
            return existing.Count == 1
                ? RenameAlbumResult.Success(existing[0].Id)
                : RenameAlbumResult.Missing();
        }

        var albumsResult = await GetAlbumsAsync(cancellationToken);
        if (!albumsResult.IsSuccess)
        {
            return RenameAlbumResult.Failure(albumsResult.StatusCode, albumsResult.ErrorMessage);
        }

        var matches = FindExactAlbumMatches(albumsResult.Albums, oldNormalized);
        if (matches.Count == 0)
        {
            return RenameAlbumResult.Missing();
        }

        if (matches.Count > 1)
        {
            return RenameAlbumResult.Failure(null, BuildDuplicateAlbumError(oldNormalized));
        }

        if (FindExactAlbumMatches(albumsResult.Albums, newNormalized).Count > 0)
        {
            return RenameAlbumResult.Failure(
                HttpStatusCode.Conflict,
                $"An album named '{newNormalized}' already exists on Immich; the rename was skipped.");
        }

        var albumId = matches[0].Id;
        var result = await SendJsonAsync(
            HttpMethod.Patch,
            ImmichApiRoutes.AlbumInfo(albumId),
            new { albumName = newNormalized },
            cancellationToken);

        if (!result.HasHttpResponse)
        {
            return RenameAlbumResult.Failure(null, result.ErrorMessage);
        }

        if (result.StatusCode == HttpStatusCode.NotFound)
        {
            return RenameAlbumResult.Missing();
        }

        if (!result.IsSuccessStatusCode)
        {
            return RenameAlbumResult.Failure(
                result.StatusCode,
                $"HTTP {(int)result.StatusCode!.Value}: {TrimForLog(result.Body)}");
        }

        return RenameAlbumResult.Success(albumId);
    }

    public async Task<UploadAssetResult> UploadAssetAsync(UploadAssetRequest request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (!File.Exists(request.FilePath))
        {
            return UploadAssetResult.Failure(null, $"File does not exist: {request.FilePath}");
        }

        var uploadResult = await UploadAssetFileAsync(request, cancellationToken);
        if (!uploadResult.IsSuccess)
        {
            return uploadResult;
        }

        var albumName = NormalizeAlbumName(request.AlbumName);
        if (string.IsNullOrWhiteSpace(albumName))
        {
            return uploadResult;
        }

        if (string.IsNullOrWhiteSpace(uploadResult.AssetId))
        {
            return UploadAssetResult.Failure(
                null,
                $"Immich did not return an asset id, so the upload could not be placed into album '{albumName}'.");
        }

        var albumResolution = await ResolveOrCreateAlbumAsync(albumName, cancellationToken);
        if (!albumResolution.IsSuccess)
        {
            return UploadAssetResult.Failure(albumResolution.StatusCode, albumResolution.ErrorMessage ?? "Album resolution failed.");
        }

        var addResult = await AddAssetsToAlbumByIdAsync(albumResolution.AlbumId!, new[] { uploadResult.AssetId }, cancellationToken);
        if (!addResult.IsSuccess)
        {
            return UploadAssetResult.Failure(addResult.StatusCode, addResult.ErrorMessage ?? "Adding the asset to the album failed.");
        }

        return uploadResult;
    }

    private async Task<UploadAssetResult> UploadAssetFileAsync(UploadAssetRequest request, CancellationToken cancellationToken)
    {
        for (var attempt = 1; attempt <= _retrySettings.MaxAttempts; attempt++)
        {
            try
            {
                var uploadResponse = await SendUploadRequestAsync(request, includeLegacyIdentifiers: false, cancellationToken);
                if (ShouldRetryUploadWithLegacyIdentifiers(uploadResponse.StatusCode, uploadResponse.Body))
                {
                    _logger.LogDebug(
                        "Upload without legacy Immich device identifiers failed with HTTP {StatusCode}. Retrying with legacy identifiers for older Immich servers.",
                        (int)uploadResponse.StatusCode);

                    uploadResponse = await SendUploadRequestAsync(request, includeLegacyIdentifiers: true, cancellationToken);
                }

                if (uploadResponse.IsSuccessStatusCode)
                {
                    var assetId = TryExtractId(uploadResponse.Body);
                    return UploadAssetResult.Success(assetId);
                }

                LogKnownHttpErrors(uploadResponse.StatusCode, request.FilePath);

                if (IsTransientStatusCode(uploadResponse.StatusCode) && attempt < _retrySettings.MaxAttempts)
                {
                    var delay = CalculateBackoff(attempt, _retrySettings.BaseDelayMilliseconds);
                    _logger.LogWarning(
                        "Upload attempt {Attempt}/{MaxAttempts} failed with HTTP {StatusCode}. Retrying in {DelayMs} ms for file {FilePath}.",
                        attempt,
                        _retrySettings.MaxAttempts,
                        (int)uploadResponse.StatusCode,
                        delay.TotalMilliseconds,
                        request.FilePath);

                    await Task.Delay(delay, cancellationToken);
                    continue;
                }

                return UploadAssetResult.Failure(
                    uploadResponse.StatusCode,
                    $"HTTP {(int)uploadResponse.StatusCode}: {TrimForLog(uploadResponse.Body)}");
            }
            catch (HttpRequestException ex) when (attempt < _retrySettings.MaxAttempts)
            {
                var delay = CalculateBackoff(attempt, _retrySettings.BaseDelayMilliseconds);
                _logger.LogWarning(
                    ex,
                    "Network error on attempt {Attempt}/{MaxAttempts}. Retrying in {DelayMs} ms for file {FilePath}.",
                    attempt,
                    _retrySettings.MaxAttempts,
                    delay.TotalMilliseconds,
                    request.FilePath);

                await Task.Delay(delay, cancellationToken);
            }
            catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested && attempt < _retrySettings.MaxAttempts)
            {
                var delay = CalculateBackoff(attempt, _retrySettings.BaseDelayMilliseconds);
                _logger.LogWarning(
                    ex,
                    "Upload timeout on attempt {Attempt}/{MaxAttempts}. Retrying in {DelayMs} ms for file {FilePath}.",
                    attempt,
                    _retrySettings.MaxAttempts,
                    delay.TotalMilliseconds,
                    request.FilePath);

                await Task.Delay(delay, cancellationToken);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Upload failed for file {FilePath}.", request.FilePath);
                return UploadAssetResult.Failure(null, ex.Message);
            }
        }

        return UploadAssetResult.Failure(null, "Upload failed after maximum retry attempts.");
    }

    private async Task<AssetSearchResult> SearchAssetsAsync(
        Func<int, object> createPayload,
        string parseErrorMessage,
        CancellationToken cancellationToken)
    {
        var collected = new List<AlbumAssetSummary>();
        var page = 1;

        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var result = await SendJsonAsync(
                HttpMethod.Post,
                ImmichApiRoutes.SearchMetadata,
                createPayload(page),
                cancellationToken);

            if (!result.HasHttpResponse)
            {
                return AssetSearchResult.Failure(null, result.ErrorMessage);
            }

            if (!result.IsSuccessStatusCode)
            {
                return AssetSearchResult.Failure(
                    result.StatusCode,
                    $"HTTP {(int)result.StatusCode!.Value}: {TrimForLog(result.Body)}");
            }

            if (!TryParseSearchAssets(result.Body, out var pageAssets, out var hasNextPage))
            {
                return AssetSearchResult.Failure(result.StatusCode, parseErrorMessage);
            }

            collected.AddRange(pageAssets);

            if (!hasNextPage || pageAssets.Count == 0)
            {
                break;
            }

            page++;
            if (page > 500)
            {
                break;
            }
        }

        return AssetSearchResult.Success(collected);
    }

    private async Task<AlbumResolutionResult> ResolveOrCreateAlbumAsync(string albumName, CancellationToken cancellationToken)
    {
        var albumsResult = await GetAlbumsAsync(cancellationToken);
        if (!albumsResult.IsSuccess)
        {
            return AlbumResolutionResult.Failure(
                albumsResult.StatusCode,
                $"Failed to list Immich albums for '{albumName}': {albumsResult.ErrorMessage}");
        }

        var exactMatches = FindExactAlbumMatches(albumsResult.Albums, albumName);
        if (exactMatches.Count > 1)
        {
            return AlbumResolutionResult.Failure(null, BuildDuplicateAlbumError(albumName));
        }

        if (exactMatches.Count == 1)
        {
            return AlbumResolutionResult.Success(exactMatches[0].Id);
        }

        var createResult = await CreateAlbumAsync(albumName, cancellationToken);
        if (createResult.IsSuccess)
        {
            return createResult;
        }

        if (createResult.StatusCode == HttpStatusCode.Conflict)
        {
            var retryAlbumsResult = await GetAlbumsAsync(cancellationToken);
            if (!retryAlbumsResult.IsSuccess)
            {
                return AlbumResolutionResult.Failure(
                    retryAlbumsResult.StatusCode,
                    $"Immich reported a conflict while creating album '{albumName}', and the follow-up lookup failed: {retryAlbumsResult.ErrorMessage}");
            }

            var retryMatches = FindExactAlbumMatches(retryAlbumsResult.Albums, albumName);
            if (retryMatches.Count > 1)
            {
                return AlbumResolutionResult.Failure(null, BuildDuplicateAlbumError(albumName));
            }

            if (retryMatches.Count == 1)
            {
                return AlbumResolutionResult.Success(retryMatches[0].Id);
            }
        }

        return createResult;
    }

    private async Task<AlbumsResult> GetAlbumsAsync(CancellationToken cancellationToken)
    {
        var result = await SendAsync(HttpMethod.Get, ImmichApiRoutes.Albums, content: null, cancellationToken);
        if (!result.HasHttpResponse)
        {
            return AlbumsResult.Failure(null, result.ErrorMessage);
        }

        if (!result.IsSuccessStatusCode)
        {
            return AlbumsResult.Failure(result.StatusCode, $"HTTP {(int)result.StatusCode!.Value}: {TrimForLog(result.Body)}");
        }

        if (result.StatusCode == HttpStatusCode.NoContent || string.IsNullOrWhiteSpace(result.Body))
        {
            return AlbumsResult.Success([]);
        }

        return TryParseAlbums(result.Body, out var albums)
            ? AlbumsResult.Success(albums)
            : AlbumsResult.Failure(result.StatusCode, "The album list response could not be parsed.");
    }

    private async Task<AlbumResolutionResult> CreateAlbumAsync(string albumName, CancellationToken cancellationToken)
    {
        var result = await SendJsonAsync(
            HttpMethod.Post,
            ImmichApiRoutes.Albums,
            new
            {
                albumName,
            },
            cancellationToken);

        if (!result.HasHttpResponse)
        {
            return AlbumResolutionResult.Failure(null, $"Creating album '{albumName}' failed: {result.ErrorMessage}");
        }

        if (!result.IsSuccessStatusCode)
        {
            return AlbumResolutionResult.Failure(
                result.StatusCode,
                $"Creating album '{albumName}' failed with HTTP {(int)result.StatusCode!.Value}: {TrimForLog(result.Body)}");
        }

        if (TryExtractAlbum(result.Body, out var album))
        {
            return AlbumResolutionResult.Success(album.Id);
        }

        var albumsResult = await GetAlbumsAsync(cancellationToken);
        if (!albumsResult.IsSuccess)
        {
            return AlbumResolutionResult.Failure(
                albumsResult.StatusCode,
                $"Album '{albumName}' was created, but the follow-up lookup failed: {albumsResult.ErrorMessage}");
        }

        var matches = FindExactAlbumMatches(albumsResult.Albums, albumName);
        if (matches.Count > 1)
        {
            return AlbumResolutionResult.Failure(null, BuildDuplicateAlbumError(albumName));
        }

        if (matches.Count == 1)
        {
            return AlbumResolutionResult.Success(matches[0].Id);
        }

        return AlbumResolutionResult.Failure(null, $"Album '{albumName}' was created, but Immich did not return a usable album id.");
    }

    private async Task<AlbumOperationResult> AddAssetsToAlbumByIdAsync(string albumId, IReadOnlyList<string> assetIds, CancellationToken cancellationToken)
    {
        if (assetIds.Count == 0)
        {
            return AlbumOperationResult.Success();
        }

        var primaryResult = await SendJsonAsync(
            HttpMethod.Put,
            ImmichApiRoutes.AlbumAssets(albumId),
            new
            {
                ids = assetIds,
            },
            cancellationToken);

        if (primaryResult.IsSuccessStatusCode)
        {
            return AlbumOperationResult.Success();
        }

        if (!primaryResult.HasHttpResponse)
        {
            return AlbumOperationResult.Failure(null, $"Adding assets to album '{albumId}' failed: {primaryResult.ErrorMessage}");
        }

        if (primaryResult.StatusCode is not HttpStatusCode.NotFound and not HttpStatusCode.MethodNotAllowed)
        {
            return AlbumOperationResult.Failure(
                primaryResult.StatusCode,
                $"Adding assets to album '{albumId}' failed with HTTP {(int)primaryResult.StatusCode!.Value}: {TrimForLog(primaryResult.Body)}");
        }

        var fallbackCandidates = new[]
        {
            new AlbumAssetRouteCandidate(
                HttpMethod.Put,
                ImmichApiRoutes.AlbumsAssets,
                new
                {
                    albumIds = new[] { albumId },
                    assetIds,
                }),
            new AlbumAssetRouteCandidate(
                HttpMethod.Post,
                ImmichApiRoutes.AlbumsAssets,
                new
                {
                    albumIds = new[] { albumId },
                    assetIds,
                }),
            new AlbumAssetRouteCandidate(
                HttpMethod.Put,
                ImmichApiRoutes.AlbumsAssets,
                new
                {
                    albumId,
                    ids = assetIds,
                }),
            new AlbumAssetRouteCandidate(
                HttpMethod.Post,
                ImmichApiRoutes.AlbumsAssets,
                new
                {
                    albumId,
                    ids = assetIds,
                }),
        };

        foreach (var candidate in fallbackCandidates)
        {
            var fallbackResult = await SendJsonAsync(candidate.Method, candidate.Route, candidate.Payload, cancellationToken);
            if (fallbackResult.IsSuccessStatusCode)
            {
                return AlbumOperationResult.Success();
            }

            if (!fallbackResult.HasHttpResponse)
            {
                return AlbumOperationResult.Failure(null, $"Adding assets to album '{albumId}' failed: {fallbackResult.ErrorMessage}");
            }

            if (fallbackResult.StatusCode is HttpStatusCode.NotFound or HttpStatusCode.MethodNotAllowed)
            {
                continue;
            }

            return AlbumOperationResult.Failure(
                fallbackResult.StatusCode,
                $"Adding assets to album '{albumId}' failed with HTTP {(int)fallbackResult.StatusCode!.Value}: {TrimForLog(fallbackResult.Body)}");
        }

        return AlbumOperationResult.Failure(
            primaryResult.StatusCode,
            "Adding assets to the album failed because the current Immich album-assignment endpoint shape was not available.");
    }

    private async Task<bool> TryPingRouteAsync(string route, CancellationToken cancellationToken)
    {
        try
        {
            using var response = await _httpClient.GetAsync(route, cancellationToken);
            if (response.IsSuccessStatusCode)
            {
                _logger.LogInformation("Immich connectivity verified using endpoint {Route}.", route);
                return true;
            }

            if (response.StatusCode == HttpStatusCode.NotFound)
            {
                _logger.LogDebug("Immich ping endpoint {Route} was not found.", route);
                return false;
            }

            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            throw new HttpRequestException(
                $"Ping endpoint '{route}' failed with HTTP {(int)response.StatusCode}: {TrimForLog(body)}");
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Ping check failed for endpoint {Route}.", route);
            return false;
        }
    }

    private async Task<bool> TryLightweightFallbackAsync(CancellationToken cancellationToken)
    {
        try
        {
            using var response = await _httpClient.GetAsync(ImmichApiRoutes.ServerInfo, cancellationToken);
            if (response.IsSuccessStatusCode)
            {
                _logger.LogInformation("Immich connectivity verified using fallback endpoint {Route}.", ImmichApiRoutes.ServerInfo);
                return true;
            }

            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            _logger.LogError(
                "Immich fallback connectivity check failed with HTTP {StatusCode}. Response: {Response}",
                (int)response.StatusCode,
                TrimForLog(body));

            return false;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Immich fallback connectivity check failed.");
            return false;
        }
    }

    private async Task<UploadHttpResult> SendUploadRequestAsync(
        UploadAssetRequest request,
        bool includeLegacyIdentifiers,
        CancellationToken cancellationToken)
    {
        using var content = CreateUploadContent(request, includeLegacyIdentifiers);
        using var response = await _httpClient.PostAsync(ImmichApiRoutes.AssetUpload, content, cancellationToken);
        var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        return new UploadHttpResult(response.StatusCode, responseBody);
    }

    private static bool ShouldRetryUploadWithLegacyIdentifiers(HttpStatusCode statusCode, string responseBody)
    {
        return statusCode is HttpStatusCode.BadRequest or HttpStatusCode.UnprocessableEntity
            && (responseBody.Contains("deviceAssetId", StringComparison.OrdinalIgnoreCase)
                || responseBody.Contains("deviceId", StringComparison.OrdinalIgnoreCase));
    }

    private static MultipartFormDataContent CreateUploadContent(UploadAssetRequest request, bool includeLegacyIdentifiers)
    {
        var fileInfo = new FileInfo(request.FilePath);
        var multipart = new MultipartFormDataContent();

        var stream = new FileStream(
            request.FilePath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.ReadWrite);

        var fileContent = new StreamContent(stream);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");

        multipart.Add(fileContent, "assetData", fileInfo.Name);
        multipart.Add(new StringContent(fileInfo.Name), "filename");
        if (includeLegacyIdentifiers)
        {
            multipart.Add(new StringContent(CreateDeviceAssetId(fileInfo)), "deviceAssetId");
            multipart.Add(new StringContent("immich-folder-watch"), "deviceId");
        }

        multipart.Add(new StringContent(fileInfo.CreationTimeUtc.ToString("O", CultureInfo.InvariantCulture)), "fileCreatedAt");
        multipart.Add(new StringContent(fileInfo.LastWriteTimeUtc.ToString("O", CultureInfo.InvariantCulture)), "fileModifiedAt");
        multipart.Add(new StringContent("false"), "isFavorite");

        return multipart;
    }

    private async Task<ApiCallResult> SendJsonAsync(HttpMethod method, string route, object payload, CancellationToken cancellationToken)
    {
        return await SendAsync(method, route, CreateJsonContent(payload), cancellationToken);
    }

    private async Task<ApiCallResult> SendAsync(HttpMethod method, string route, HttpContent? content, CancellationToken cancellationToken)
    {
        try
        {
            using var request = new HttpRequestMessage(method, route)
            {
                Content = content,
            };

            using var response = await _httpClient.SendAsync(request, cancellationToken);
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            return ApiCallResult.FromResponse(response.StatusCode, body);
        }
        catch (Exception ex)
        {
            return ApiCallResult.FromException(ex.Message);
        }
    }

    private static StringContent CreateJsonContent<T>(T payload)
    {
        return new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
    }

    private static string CreateDeviceAssetId(FileInfo fileInfo)
    {
        var input = $"{fileInfo.FullName}|{fileInfo.Length}|{fileInfo.LastWriteTimeUtc.Ticks}";
        var hashBytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(hashBytes).ToLowerInvariant();
    }

    private static string NormalizeAlbumName(string value)
    {
        return (value ?? string.Empty).Trim();
    }

    private static List<AlbumSummary> FindExactAlbumMatches(IReadOnlyList<AlbumSummary> albums, string albumName)
    {
        return albums
            .Where(album => string.Equals(album.Name, albumName, StringComparison.Ordinal))
            .ToList();
    }

    private static string BuildDuplicateAlbumError(string albumName)
    {
        return $"Multiple Immich albums named '{albumName}' already exist. Rename or remove duplicates so uploads can be assigned unambiguously.";
    }

    private static bool TryParseAlbums(string responseBody, out List<AlbumSummary> albums)
    {
        albums = new List<AlbumSummary>();

        try
        {
            using var document = JsonDocument.Parse(responseBody);
            JsonElement albumArrayElement;
            if (document.RootElement.ValueKind == JsonValueKind.Array)
            {
                albumArrayElement = document.RootElement;
            }
            else if (document.RootElement.ValueKind == JsonValueKind.Object
                && TryGetAlbumArrayElement(document.RootElement, out var nestedArray))
            {
                albumArrayElement = nestedArray;
            }
            else
            {
                return false;
            }

            foreach (var element in albumArrayElement.EnumerateArray())
            {
                if (TryExtractAlbum(element, out var album))
                {
                    albums.Add(album);
                }
            }

            return true;
        }
        catch (JsonException)
        {
            albums = new List<AlbumSummary>();
            return false;
        }
    }

    private static bool TryGetAlbumArrayElement(JsonElement root, out JsonElement albumArray)
    {
        if (root.TryGetProperty("albums", out albumArray) && albumArray.ValueKind == JsonValueKind.Array)
        {
            return true;
        }

        if (root.TryGetProperty("items", out albumArray) && albumArray.ValueKind == JsonValueKind.Array)
        {
            return true;
        }

        albumArray = default;
        return false;
    }

    private static bool TryParseSearchAssets(string responseBody, out List<AlbumAssetSummary> assets, out bool hasNextPage)
    {
        assets = new List<AlbumAssetSummary>();
        hasNextPage = false;

        if (string.IsNullOrWhiteSpace(responseBody))
        {
            return true;
        }

        try
        {
            using var document = JsonDocument.Parse(responseBody);
            JsonElement itemsElement;

            if (document.RootElement.ValueKind == JsonValueKind.Array)
            {
                itemsElement = document.RootElement;
            }
            else if (document.RootElement.ValueKind == JsonValueKind.Object
                && TryGetSearchItemsElement(document.RootElement, out itemsElement, out hasNextPage))
            {
                // itemsElement is now set
            }
            else
            {
                return false;
            }

            foreach (var element in itemsElement.EnumerateArray())
            {
                if (element.ValueKind != JsonValueKind.Object)
                {
                    continue;
                }

                if (!TryExtractString(element, "id", out var id))
                {
                    continue;
                }

                if (!TryExtractString(element, "originalFileName", out var originalFileName)
                    && !TryExtractString(element, "originalPath", out originalFileName))
                {
                    originalFileName = id;
                }

                assets.Add(new AlbumAssetSummary(id, Path.GetFileName(originalFileName)));
            }

            return true;
        }
        catch (JsonException)
        {
            assets = new List<AlbumAssetSummary>();
            hasNextPage = false;
            return false;
        }
    }

    private static bool TryGetSearchItemsElement(JsonElement root, out JsonElement itemsElement, out bool hasNextPage)
    {
        itemsElement = default;
        hasNextPage = false;

        if (root.TryGetProperty("assets", out var assetsElement))
        {
            if (assetsElement.ValueKind == JsonValueKind.Array)
            {
                itemsElement = assetsElement;
                return true;
            }

            if (assetsElement.ValueKind == JsonValueKind.Object
                && assetsElement.TryGetProperty("items", out var items)
                && items.ValueKind == JsonValueKind.Array)
            {
                itemsElement = items;

                if (assetsElement.TryGetProperty("nextPage", out var nextPage))
                {
                    hasNextPage = nextPage.ValueKind switch
                    {
                        JsonValueKind.Number => true,
                        JsonValueKind.String => !string.IsNullOrWhiteSpace(nextPage.GetString()),
                        _ => false,
                    };
                }

                return true;
            }
        }

        if (root.TryGetProperty("items", out var topItems) && topItems.ValueKind == JsonValueKind.Array)
        {
            itemsElement = topItems;
            return true;
        }

        return false;
    }

    private static bool TryExtractAlbum(string responseBody, out AlbumSummary album)
    {
        album = default;

        if (string.IsNullOrWhiteSpace(responseBody))
        {
            return false;
        }

        try
        {
            using var document = JsonDocument.Parse(responseBody);
            return TryExtractAlbum(document.RootElement, out album);
        }
        catch (JsonException)
        {
            album = default;
            return false;
        }
    }

    private static bool TryExtractAlbum(JsonElement element, out AlbumSummary album)
    {
        album = default;

        if (element.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        if (!TryExtractString(element, "id", out var id))
        {
            return false;
        }

        if (!TryExtractString(element, "albumName", out var albumName)
            && !TryExtractString(element, "name", out albumName))
        {
            return false;
        }

        album = new AlbumSummary(id, albumName.Trim());
        return true;
    }

    private static bool TryExtractString(JsonElement element, string propertyName, out string value)
    {
        value = string.Empty;

        if (!element.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        value = property.GetString() ?? string.Empty;
        return !string.IsNullOrWhiteSpace(value);
    }

    private static string? TryExtractId(string responseBody)
    {
        if (string.IsNullOrWhiteSpace(responseBody))
        {
            return null;
        }

        try
        {
            using var document = JsonDocument.Parse(responseBody);
            return document.RootElement.TryGetProperty("id", out var idElement) && idElement.ValueKind == JsonValueKind.String
                ? idElement.GetString()
                : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static bool IsTransientStatusCode(HttpStatusCode statusCode)
    {
        return statusCode == HttpStatusCode.RequestTimeout
            || statusCode == HttpStatusCode.TooManyRequests
            || statusCode == HttpStatusCode.InternalServerError
            || statusCode == HttpStatusCode.BadGateway
            || statusCode == HttpStatusCode.ServiceUnavailable
            || statusCode == HttpStatusCode.GatewayTimeout;
    }

    private static string TrimForLog(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        return value.Length <= 512 ? value : value[..512];
    }

    private static TimeSpan CalculateBackoff(int attempt, int baseDelayMilliseconds)
    {
        var factor = Math.Pow(2, attempt - 1);
        var delayMilliseconds = Math.Min(factor * baseDelayMilliseconds, MaxBackoffMilliseconds);
        return TimeSpan.FromMilliseconds(delayMilliseconds);
    }

    private void LogKnownHttpErrors(HttpStatusCode statusCode, string filePath)
    {
        if (statusCode == HttpStatusCode.Unauthorized)
        {
            _logger.LogError("Upload failed with HTTP 401 for file {FilePath}. Check your Immich API key.", filePath);
            return;
        }

        if (statusCode == HttpStatusCode.RequestEntityTooLarge)
        {
            _logger.LogError("Upload failed with HTTP 413 for file {FilePath}. File is too large for the server limits.", filePath);
            return;
        }

        if ((int)statusCode >= 500)
        {
            _logger.LogWarning("Upload failed with server error HTTP {StatusCode} for file {FilePath}.", (int)statusCode, filePath);
        }
    }

    private readonly record struct AlbumSummary(string Id, string Name);

    private readonly record struct AlbumAssetRouteCandidate(HttpMethod Method, string Route, object Payload);

    private readonly record struct AssetSearchResult(bool IsSuccess, IReadOnlyList<AlbumAssetSummary> Assets, HttpStatusCode? StatusCode, string ErrorMessage)
    {
        public static AssetSearchResult Success(IReadOnlyList<AlbumAssetSummary> assets)
        {
            return new AssetSearchResult(true, assets, null, string.Empty);
        }

        public static AssetSearchResult Failure(HttpStatusCode? statusCode, string errorMessage)
        {
            return new AssetSearchResult(false, Array.Empty<AlbumAssetSummary>(), statusCode, errorMessage);
        }
    }

    private readonly record struct AlbumsResult(bool IsSuccess, IReadOnlyList<AlbumSummary> Albums, HttpStatusCode? StatusCode, string ErrorMessage)
    {
        public static AlbumsResult Success(IReadOnlyList<AlbumSummary> albums)
        {
            return new AlbumsResult(true, albums, null, string.Empty);
        }

        public static AlbumsResult Failure(HttpStatusCode? statusCode, string errorMessage)
        {
            return new AlbumsResult(false, Array.Empty<AlbumSummary>(), statusCode, errorMessage);
        }
    }

    private readonly record struct AlbumResolutionResult(bool IsSuccess, string? AlbumId, HttpStatusCode? StatusCode, string? ErrorMessage)
    {
        public static AlbumResolutionResult Success(string albumId)
        {
            return new AlbumResolutionResult(true, albumId, null, null);
        }

        public static AlbumResolutionResult Failure(HttpStatusCode? statusCode, string errorMessage)
        {
            return new AlbumResolutionResult(false, null, statusCode, errorMessage);
        }
    }

    private readonly record struct AlbumOperationResult(bool IsSuccess, HttpStatusCode? StatusCode, string? ErrorMessage)
    {
        public static AlbumOperationResult Success()
        {
            return new AlbumOperationResult(true, null, null);
        }

        public static AlbumOperationResult Failure(HttpStatusCode? statusCode, string errorMessage)
        {
            return new AlbumOperationResult(false, statusCode, errorMessage);
        }
    }

    private readonly record struct ApiCallResult(HttpStatusCode? StatusCode, string Body, string ErrorMessage)
    {
        public bool HasHttpResponse => StatusCode.HasValue;

        public bool IsSuccessStatusCode => StatusCode is >= HttpStatusCode.OK and < HttpStatusCode.MultipleChoices;

        public static ApiCallResult FromResponse(HttpStatusCode statusCode, string body)
        {
            return new ApiCallResult(statusCode, body, string.Empty);
        }

        public static ApiCallResult FromException(string errorMessage)
        {
            return new ApiCallResult(null, string.Empty, errorMessage);
        }
    }

    private readonly record struct UploadHttpResult(HttpStatusCode StatusCode, string Body)
    {
        public bool IsSuccessStatusCode => StatusCode is >= HttpStatusCode.OK and < HttpStatusCode.MultipleChoices;
    }
}
