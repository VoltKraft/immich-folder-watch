namespace ImmichFolderWatch.Core.Models;

public sealed class AdminCommand
{
    public AdminCommand(AdminCommandKind kind, string? sourcePath, string? resultFilePath)
    {
        Kind = kind;
        SourcePath = sourcePath;
        ResultFilePath = resultFilePath;
    }

    public AdminCommandKind Kind { get; }

    public string? SourcePath { get; }

    public string? ResultFilePath { get; }
}
