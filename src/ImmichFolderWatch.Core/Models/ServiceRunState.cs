namespace ImmichFolderWatch.Core.Models;

public enum ServiceRunState
{
    Unknown = 0,
    NotInstalled = 1,
    Running = 2,
    Stopped = 3,
    StartPending = 4,
    StopPending = 5,
    Paused = 6,
}
