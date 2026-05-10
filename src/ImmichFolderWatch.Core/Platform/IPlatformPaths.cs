namespace ImmichFolderWatch.Core.Platform;

public interface IPlatformPaths
{
    string ProductFolderName { get; }

    string GetUserDataRoot();

    string GetConfigPath();

    string GetLogDirectory();
}
