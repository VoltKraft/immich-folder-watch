namespace ImmichFolderWatch.Core.Models;

public sealed class AdminCommand
{
    public AdminCommand(AdminCommandKind kind, string? sourcePath, string? resultFilePath, string? legacyInstallRoot = null)
    {
        Kind = kind;
        SourcePath = sourcePath;
        ResultFilePath = resultFilePath;
        LegacyInstallRoot = legacyInstallRoot;
    }

    public AdminCommandKind Kind { get; }

    public string? SourcePath { get; }

    public string? ResultFilePath { get; }

    public string? LegacyInstallRoot { get; }
}
