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

public sealed class ImmichAssetClient : IImmichAssetClient
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

    public async Task<UploadAssetResult> UploadAssetAsync(UploadAssetRequest request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (!File.Exists(request.FilePath))
        {
            return UploadAssetResult.Failure(null, $"File does not exist: {request.FilePath}");
        }

        for (var attempt = 1; attempt <= _retrySettings.MaxAttempts; attempt++)
        {
            try
            {
                using var content = CreateUploadContent(request);
                using var response = await _httpClient.PostAsync(ImmichApiRoutes.AssetUpload, content, cancellationToken);
                var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);

                if (response.IsSuccessStatusCode)
                {
                    var assetId = TryExtractAssetId(responseBody);
                    return UploadAssetResult.Success(assetId);
                }

                LogKnownHttpErrors(response.StatusCode, request.FilePath);

                if (IsTransientStatusCode(response.StatusCode) && attempt < _retrySettings.MaxAttempts)
                {
                    var delay = CalculateBackoff(attempt, _retrySettings.BaseDelayMilliseconds);
                    _logger.LogWarning(
                        "Upload attempt {Attempt}/{MaxAttempts} failed with HTTP {StatusCode}. Retrying in {DelayMs} ms for file {FilePath}.",
                        attempt,
                        _retrySettings.MaxAttempts,
                        (int)response.StatusCode,
                        delay.TotalMilliseconds,
                        request.FilePath);

                    await Task.Delay(delay, cancellationToken);
                    continue;
                }

                return UploadAssetResult.Failure(
                    response.StatusCode,
                    $"HTTP {(int)response.StatusCode}: {TrimForLog(responseBody)}");
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

    private static MultipartFormDataContent CreateUploadContent(UploadAssetRequest request)
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
        multipart.Add(new StringContent(CreateDeviceAssetId(fileInfo)), "deviceAssetId");
        multipart.Add(new StringContent("immich-folder-watch"), "deviceId");
        multipart.Add(new StringContent(fileInfo.CreationTimeUtc.ToString("O", CultureInfo.InvariantCulture)), "fileCreatedAt");
        multipart.Add(new StringContent(fileInfo.LastWriteTimeUtc.ToString("O", CultureInfo.InvariantCulture)), "fileModifiedAt");
        multipart.Add(new StringContent("false"), "isFavorite");
        multipart.Add(new StringContent("false"), "isArchived");

        return multipart;
    }

    private static string CreateDeviceAssetId(FileInfo fileInfo)
    {
        var input = $"{fileInfo.FullName}|{fileInfo.Length}|{fileInfo.LastWriteTimeUtc.Ticks}";
        var hashBytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(hashBytes).ToLowerInvariant();
    }

    private static string? TryExtractAssetId(string responseBody)
    {
        if (string.IsNullOrWhiteSpace(responseBody))
        {
            return null;
        }

        try
        {
            using var document = JsonDocument.Parse(responseBody);
            if (document.RootElement.TryGetProperty("id", out var idElement) && idElement.ValueKind == JsonValueKind.String)
            {
                return idElement.GetString();
            }
        }
        catch (JsonException)
        {
        }

        return null;
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
}
