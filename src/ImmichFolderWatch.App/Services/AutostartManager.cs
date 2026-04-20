using System.Runtime.InteropServices;
using ImmichFolderWatch.Core.Installation;

namespace ImmichFolderWatch.App.Services;

public sealed class AutostartManager
{
    public const string AutostartArgument = "--autostart";

    public bool IsEnabled()
    {
        return File.Exists(InstallationPaths.GetStartupShortcutPath());
    }

    public void Enable()
    {
        var shortcutPath = InstallationPaths.GetStartupShortcutPath();
        var directory = Path.GetDirectoryName(shortcutPath);
        if (!string.IsNullOrWhiteSpace(directory))
        {
            Directory.CreateDirectory(directory);
        }

        var targetPath = GetAppExecutablePath();
        CreateShortcut(
            shortcutPath,
            targetPath,
            AutostartArgument,
            Path.GetDirectoryName(targetPath) ?? string.Empty,
            "Immich Folder Watch",
            targetPath);
    }

    public void Disable()
    {
        var shortcutPath = InstallationPaths.GetStartupShortcutPath();
        if (File.Exists(shortcutPath))
        {
            File.Delete(shortcutPath);
        }
    }

    private static string GetAppExecutablePath()
    {
        var processPath = Environment.ProcessPath;
        if (!string.IsNullOrWhiteSpace(processPath))
        {
            return processPath;
        }

        return InstallationPaths.GetAppExecutablePath(AppContext.BaseDirectory);
    }

    private static void CreateShortcut(
        string shortcutPath,
        string targetPath,
        string arguments,
        string workingDirectory,
        string description,
        string iconLocation)
    {
        var shellType = Type.GetTypeFromProgID("WScript.Shell")
            ?? throw new InvalidOperationException("WScript.Shell COM type is not available.");

        dynamic? shell = null;
        dynamic? shortcut = null;
        try
        {
            shell = Activator.CreateInstance(shellType)!;
            shortcut = shell.CreateShortcut(shortcutPath);
            shortcut.TargetPath = targetPath;
            shortcut.Arguments = arguments;
            shortcut.WorkingDirectory = workingDirectory;
            shortcut.Description = description;
            shortcut.IconLocation = iconLocation;
            shortcut.Save();
        }
        finally
        {
            if (shortcut is not null)
            {
                Marshal.FinalReleaseComObject(shortcut);
            }

            if (shell is not null)
            {
                Marshal.FinalReleaseComObject(shell);
            }
        }
    }
}
