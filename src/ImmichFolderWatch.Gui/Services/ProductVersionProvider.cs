using System.Reflection;

namespace ImmichFolderWatch.Gui.Services;

internal static class ProductVersionProvider
{
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

        return "1.3.1";
    }
}
