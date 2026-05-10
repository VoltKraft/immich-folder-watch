using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Core.Logging;

public sealed class WindowsLoggingCapabilities : IPlatformLoggingCapabilities
{
    public IReadOnlyList<string> SupportedTargets { get; } =
        new[] { LogTargets.EventLog, LogTargets.File };

    public string DefaultTarget => LogTargets.EventLog;

    public string CoerceToSupported(string? target)
    {
        var normalized = LogTargets.Normalize(target);
        return SupportedTargets.Contains(normalized) ? normalized : DefaultTarget;
    }
}
