namespace ImmichFolderWatch.Gui.Models;

public sealed class ImmichPermissionStatusItem
{
    public string DisplayName { get; init; } = string.Empty;

    public string PermissionName { get; init; } = string.Empty;

    public string StatusText { get; init; } = string.Empty;

    public StatusTone StatusTone { get; init; } = StatusTone.Neutral;

    public string Message { get; init; } = string.Empty;
}
