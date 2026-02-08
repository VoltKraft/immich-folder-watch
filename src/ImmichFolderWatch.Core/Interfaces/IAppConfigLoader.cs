using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IAppConfigLoader
{
    AppConfig Load(string configPath);
}
