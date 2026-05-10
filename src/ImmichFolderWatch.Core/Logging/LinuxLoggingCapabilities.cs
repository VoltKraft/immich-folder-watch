using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Core.Logging;

public sealed class LinuxLoggingCapabilities : IPlatformLoggingCapabilities
{
    public IReadOnlyList<string> SupportedTargets { get; } =
        new[] { LogTargets.Journald, LogTargets.File };

    public string DefaultTarget => LogTargets.Journald;

    public string CoerceToSupported(string? target)
    {
        var normalized = LogTargets.Normalize(target);
        return SupportedTargets.Contains(normalized) ? normalized : DefaultTarget;
    }
}
