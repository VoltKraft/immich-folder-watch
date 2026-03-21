using System.Reflection;

namespace ImmichFolderWatch.Gui.Services;

internal static class ProductVersionProvider
{
    private const string FallbackVersion = "1.6.3";

    public static string GetProductVersion()
    {
        var informationalVersion = typeof(ProductVersionProvider)
            .Assembly
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
            ?.InformationalVersion;

        if (!string.IsNullOrWhiteSpace(informationalVersion))
        {
            var plusIndex = informationalVersion.IndexOf('+');
            return plusIndex >= 0
                ? informationalVersion[..plusIndex]
                : informationalVersion;
        }

        return FallbackVersion;
    }
}
