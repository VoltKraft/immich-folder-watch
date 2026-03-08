namespace ImmichFolderWatch.Core.Models;

public sealed class ConfigApplyActions
{
    public bool SetAutomaticDelayedStart { get; init; }

    public bool StartService { get; init; }

    public bool RestartService { get; init; }

    public bool MarkInitialVerificationCompleted { get; init; }
}
