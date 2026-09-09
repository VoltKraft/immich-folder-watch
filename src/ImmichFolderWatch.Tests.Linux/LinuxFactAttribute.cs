using System.Runtime.CompilerServices;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

/// <summary>Skips native Linux protocol checks when the solution is tested on another platform.</summary>
public sealed class LinuxFactAttribute : FactAttribute
{
    public LinuxFactAttribute(
        [CallerFilePath] string? sourceFilePath = null,
        [CallerLineNumber] int sourceLineNumber = -1)
        : base(sourceFilePath, sourceLineNumber)
    {
        if (!OperatingSystem.IsLinux())
        {
            Skip = "Requires Linux and the native D-Bus protocol test tools.";
        }
    }
}
