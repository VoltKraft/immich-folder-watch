namespace ImmichFolderWatch.Core.Models;

public sealed class ImmichPermissionCheckResult
{
    public string PermissionName { get; init; } = string.Empty;

    public string DisplayName { get; init; } = string.Empty;

    public CheckState State { get; init; } = CheckState.NotChecked;

    public string Message { get; init; } = string.Empty;

    public bool BlocksConfigVerification { get; init; }
}
