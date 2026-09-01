using System.Security.Cryptography;
using System.Text;

namespace ImmichFolderWatch.Core.Models;

public static class SyncAccountScope
{
    public static string Create(string serverApiUrl, string apiKey)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(serverApiUrl);
        ArgumentException.ThrowIfNullOrWhiteSpace(apiKey);

        var normalizedServerApiUrl = serverApiUrl.Trim().TrimEnd('/');
        var input = Encoding.UTF8.GetBytes($"{normalizedServerApiUrl}\n{apiKey}");
        return Convert.ToHexStringLower(SHA256.HashData(input));
    }
}
