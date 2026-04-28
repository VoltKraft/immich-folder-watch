using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.App.Linux.ViewModels;

public sealed class ShellViewModel : BindableBase
{
    public ShellViewModel(IPlatformPaths paths)
    {
        ArgumentNullException.ThrowIfNull(paths);

        VersionText = $"v{typeof(ShellViewModel).Assembly.GetName().Version?.ToString(3) ?? "0.0.0"}";
        ConfigPath = $"Config: {paths.GetConfigPath()}";
        LogDirectory = $"Logs:   {paths.GetLogDirectory()}";
    }

    public string VersionText { get; }

    public string ConfigPath { get; }

    public string LogDirectory { get; }
}
