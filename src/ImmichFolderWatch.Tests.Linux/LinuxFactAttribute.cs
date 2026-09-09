using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

/// <summary>Skips native Linux protocol checks when the solution is tested on another platform.</summary>
public sealed class LinuxFactAttribute : FactAttribute
{
    public LinuxFactAttribute()
    {
        if (!OperatingSystem.IsLinux())
        {
            Skip = "Requires Linux and the native D-Bus protocol test tools.";
        }
    }
}
