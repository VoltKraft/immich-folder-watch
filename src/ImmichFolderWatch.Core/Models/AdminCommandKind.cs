namespace ImmichFolderWatch.Core.Models;

public enum AdminCommandKind
{
    Status = 0,
    ApplyVerifiedConfig = 1,
    StartService = 2,
    StopService = 3,
    RestartService = 4,
    MigrateDataLayout = 5,
}
