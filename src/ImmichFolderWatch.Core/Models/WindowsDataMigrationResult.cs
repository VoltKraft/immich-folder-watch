namespace ImmichFolderWatch.Core.Models;

public sealed class WindowsDataMigrationResult
{
    public bool ConfigMigrated { get; init; }

    public bool UsedExistingConfig { get; init; }

    public bool RewroteLogDirectoryToDefault { get; init; }

    public int MovedLogFileCount { get; init; }

    public int SkippedLogFileCount { get; init; }
}
