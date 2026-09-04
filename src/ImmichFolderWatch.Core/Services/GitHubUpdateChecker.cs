using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.RegularExpressions;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Models;
using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Core.Services;

/// <summary>
/// Performs a best-effort check against the latest stable GitHub release.
/// </summary>
public sealed partial class GitHubUpdateChecker : IUpdateChecker
{
    private const string LatestReleaseUrl = "https://api.github.com/repos/VoltKraft/immich-folder-watch/releases/latest";
    private const string ReleasePageBaseUrl = "https://github.com/VoltKraft/immich-folder-watch/releases/tag/";
    private static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(5);

    private readonly HttpClient _httpClient;
    private readonly ILogger<GitHubUpdateChecker> _logger;

    public GitHubUpdateChecker(HttpClient httpClient, ILogger<GitHubUpdateChecker> logger)
    {
        ArgumentNullException.ThrowIfNull(httpClient);
        ArgumentNullException.ThrowIfNull(logger);

        _httpClient = httpClient;
        _logger = logger;
    }

    public async Task<UpdateInfo?> CheckAsync(Version currentVersion, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(currentVersion);

        try
        {
            using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeoutSource.CancelAfter(RequestTimeout);

            using var request = new HttpRequestMessage(HttpMethod.Get, LatestReleaseUrl);
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));
            request.Headers.UserAgent.Add(new ProductInfoHeaderValue("ImmichFolderWatch", GetSemanticVersion(currentVersion).ToString()));

            using var response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                timeoutSource.Token);
            response.EnsureSuccessStatusCode();

            await using var responseStream = await response.Content.ReadAsStreamAsync(timeoutSource.Token);
            using var document = await JsonDocument.ParseAsync(
                responseStream,
                cancellationToken: timeoutSource.Token);

            var root = document.RootElement;
            var tag = GetRequiredString(root, "tag_name");
            var version = ParseReleaseVersion(tag);
            var htmlUrl = GetRequiredString(root, "html_url");
            var downloadUri = ValidateDownloadUri(tag, htmlUrl);

            if (IsTrue(root, "draft") || IsTrue(root, "prerelease"))
            {
                throw new InvalidDataException("The latest GitHub release is not a stable release.");
            }

            return version > GetSemanticVersion(currentVersion)
                ? new UpdateInfo(version, downloadUri)
                : null;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "The GitHub update check failed and was ignored.");
            return null;
        }
    }

    private static string GetRequiredString(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var property)
            || property.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(property.GetString()))
        {
            throw new InvalidDataException($"The GitHub release response does not contain a valid {propertyName}.");
        }

        return property.GetString()!;
    }

    private static Version ParseReleaseVersion(string tag)
    {
        var match = ReleaseTagRegex().Match(tag);
        if (!match.Success
            || !int.TryParse(match.Groups["major"].Value, out var major)
            || !int.TryParse(match.Groups["minor"].Value, out var minor)
            || !int.TryParse(match.Groups["patch"].Value, out var patch))
        {
            throw new InvalidDataException($"The GitHub release tag '{tag}' is not a valid stable version.");
        }

        return new Version(major, minor, patch);
    }

    private static Uri ValidateDownloadUri(string tag, string htmlUrl)
    {
        var expectedUri = new Uri(ReleasePageBaseUrl + tag, UriKind.Absolute);
        if (!Uri.TryCreate(htmlUrl, UriKind.Absolute, out var downloadUri)
            || !string.Equals(downloadUri.AbsoluteUri, expectedUri.AbsoluteUri, StringComparison.Ordinal))
        {
            throw new InvalidDataException("The GitHub release response contains an unexpected download URL.");
        }

        return expectedUri;
    }

    private static bool IsTrue(JsonElement root, string propertyName)
    {
        return root.TryGetProperty(propertyName, out var property)
            && property.ValueKind == JsonValueKind.True;
    }

    private static Version GetSemanticVersion(Version version)
    {
        return new Version(version.Major, version.Minor, Math.Max(version.Build, 0));
    }

    [GeneratedRegex("^v(?<major>0|[1-9][0-9]*)\\.(?<minor>0|[1-9][0-9]*)\\.(?<patch>0|[1-9][0-9]*)$", RegexOptions.CultureInvariant)]
    private static partial Regex ReleaseTagRegex();
}
