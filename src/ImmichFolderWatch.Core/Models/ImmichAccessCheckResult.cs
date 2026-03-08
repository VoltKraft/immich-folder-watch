namespace ImmichFolderWatch.Core.Models;

public sealed class ImmichAccessCheckResult
{
    public CheckState UrlState { get; init; } = CheckState.NotChecked;

    public string UrlMessage { get; init; } = string.Empty;

    public CheckState ApiKeyState { get; init; } = CheckState.NotChecked;

    public string ApiKeyMessage { get; init; } = string.Empty;

    public CheckState PermissionsState { get; init; } = CheckState.NotChecked;

    public string PermissionsMessage { get; init; } = string.Empty;

    public IReadOnlyList<ImmichPermissionCheckResult> PermissionResults { get; init; } = Array.Empty<ImmichPermissionCheckResult>();

    public IReadOnlyList<string> GetBlockingErrors()
    {
        var errors = new List<string>();

        if (UrlState == CheckState.Failed && !string.IsNullOrWhiteSpace(UrlMessage))
        {
            errors.Add(UrlMessage);
        }

        if (ApiKeyState == CheckState.Failed && !string.IsNullOrWhiteSpace(ApiKeyMessage))
        {
            errors.Add(ApiKeyMessage);
        }

        foreach (var permissionResult in PermissionResults.Where(permission => permission.BlocksConfigVerification && permission.State == CheckState.Failed))
        {
            errors.Add($"{permissionResult.DisplayName}: {permissionResult.Message}");
        }

        return errors;
    }
}
