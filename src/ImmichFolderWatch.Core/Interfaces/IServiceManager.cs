using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IServiceManager
{
    ServiceStatusSnapshot GetStatus();

    void SetStartupType(ServiceStartupType startupType, bool delayedAutoStart);

    void StartService();

    void StopService();

    void RestartService();
}
