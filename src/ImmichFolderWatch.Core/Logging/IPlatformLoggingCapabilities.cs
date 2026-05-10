using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Core.Logging;

/// <summary>
/// Describes which <see cref="LogTargets"/> values the current platform
/// can actually honour — Linux can write to journald + file, Windows can
/// write to the EventLog + file. Lets the shared MainWindowViewModel
/// build a platform-correct dropdown without compiling a Linux constant
/// into the WPF assembly (or vice versa).
/// </summary>
public interface IPlatformLoggingCapabilities
{
    IReadOnlyList<string> SupportedTargets { get; }

    string DefaultTarget { get; }

    /// <summary>
    /// Returns <paramref name="target"/> if this platform supports it,
    /// otherwise the platform default. Used to coerce stale YAML targets
    /// (e.g. a Linux head reading a config previously saved by the WPF
    /// head with target=eventLog) into something runnable.
    /// </summary>
    string CoerceToSupported(string? target);
}
