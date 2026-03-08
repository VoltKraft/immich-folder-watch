namespace ImmichFolderWatch.Core.Models;

public sealed class ServiceStatusSnapshot
{
    public string ServiceName { get; init; } = string.Empty;

    public bool Exists { get; init; }

    public ServiceRunState State { get; init; } = ServiceRunState.Unknown;

    public ServiceStartupType StartupType { get; init; } = ServiceStartupType.Unknown;

    public bool DelayedAutoStart { get; init; }

    public bool IsInitialVerificationCompleted { get; init; }

    public string ConfigPath { get; init; } = string.Empty;

    public string LogDirectory { get; init; } = string.Empty;
}
