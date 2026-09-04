using System.Reflection;

namespace ImmichFolderWatch.App.Shared.Services;

public static class ProductVersionProvider
{
    /// <summary>
    /// Resolves the three-component product version from informational-version metadata,
    /// falling back to the assembly version when necessary.
    /// </summary>
    /// <param name="assembly">The product assembly, or <see langword="null"/> to use the process entry assembly.</param>
    /// <returns>The product version without build metadata or revision, or <see langword="null"/> when unavailable.</returns>
    public static Version? GetProductVersion(Assembly? assembly = null)
    {
        var productAssembly = assembly ?? Assembly.GetEntryAssembly();
        if (productAssembly is null)
        {
            return null;
        }

        var informationalVersion = productAssembly
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
            ?.InformationalVersion;

        if (!string.IsNullOrWhiteSpace(informationalVersion))
        {
            var metadataSeparator = informationalVersion.IndexOf('+');
            var versionText = metadataSeparator >= 0
                ? informationalVersion[..metadataSeparator]
                : informationalVersion;

            if (Version.TryParse(versionText, out var parsedVersion))
            {
                return ToThreeComponentVersion(parsedVersion);
            }
        }

        var assemblyVersion = productAssembly.GetName().Version;
        return assemblyVersion is null
            ? null
            : ToThreeComponentVersion(assemblyVersion);
    }

    private static Version ToThreeComponentVersion(Version version)
    {
        return new Version(version.Major, version.Minor, Math.Max(version.Build, 0));
    }
}
