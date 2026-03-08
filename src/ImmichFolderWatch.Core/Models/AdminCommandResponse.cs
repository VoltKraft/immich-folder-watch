namespace ImmichFolderWatch.Core.Models;

public sealed class AdminCommandResponse
{
    public bool Success { get; init; }

    public string Message { get; init; } = string.Empty;

    public ServiceStatusSnapshot? Status { get; init; }
}
