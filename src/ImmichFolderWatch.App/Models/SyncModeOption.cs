namespace ImmichFolderWatch.App.Models;

public sealed class SyncModeOption
{
    public SyncModeOption(string code, string displayName, string description)
    {
        Code = code;
        DisplayName = displayName;
        Description = description;
    }

    public string Code { get; }

    public string DisplayName { get; }

    public string Description { get; }
}
