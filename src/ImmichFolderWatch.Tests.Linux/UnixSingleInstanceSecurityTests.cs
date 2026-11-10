using ImmichFolderWatch.App.Linux.Platform;
using System.Runtime.Versioning;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

[CollectionDefinition("Instance environment", DisableParallelization = true)]
public sealed class InstanceEnvironmentCollection;

[SupportedOSPlatform("linux")]
[Collection("Instance environment")]
public sealed class UnixSingleInstanceSecurityTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), $"ifw-ipc-{Guid.NewGuid():N}");

    [LinuxFact]
    public void MissingRuntimeEnvironment_UsesPrivateUserConfigFallback()
    {
        var originalRuntime = Environment.GetEnvironmentVariable("XDG_RUNTIME_DIR");
        var originalConfig = Environment.GetEnvironmentVariable("XDG_CONFIG_HOME");
        try
        {
            Environment.SetEnvironmentVariable("XDG_RUNTIME_DIR", null);
            Environment.SetEnvironmentVariable("XDG_CONFIG_HOME", _root);
            using var coordinator = new UnixSingleInstanceCoordinator();
            var runtime = Path.Combine(_root, "immich-folder-watch", "runtime");
            Assert.True(coordinator.IsPrimaryInstance);
            Assert.True(File.Exists(Path.Combine(runtime, UnixSingleInstanceCoordinator.DefaultSocketName)));
            Assert.Equal((UnixFileMode)0x1c0, File.GetUnixFileMode(runtime));
        }
        finally
        {
            Environment.SetEnvironmentVariable("XDG_RUNTIME_DIR", originalRuntime);
            Environment.SetEnvironmentVariable("XDG_CONFIG_HOME", originalConfig);
        }
    }

    [LinuxFact]
    public void SecondaryDisposal_DoesNotUnlinkPrimarySocket()
    {
        var path = Path.Combine(_root, "instance.sock");
        using var primary = new UnixSingleInstanceCoordinator(path);
        Assert.True(primary.IsPrimaryInstance);
        using (var secondary = new UnixSingleInstanceCoordinator(path))
        {
            Assert.False(secondary.IsPrimaryInstance);
        }
        Assert.True(File.Exists(path));
        Assert.Equal((UnixFileMode)0x1c0, File.GetUnixFileMode(_root));
    }

    [LinuxFact]
    public void LinkedRuntimeDirectory_ReportsFailureInsteadOfSecondaryInstance()
    {
        Directory.CreateDirectory(_root);
        var target = Path.Combine(_root, "target");
        Directory.CreateDirectory(target);
        var link = Path.Combine(_root, "link");
        Directory.CreateSymbolicLink(link, target);
        Assert.Throws<IOException>(() => new UnixSingleInstanceCoordinator(Path.Combine(link, "instance.sock")));
        Assert.Empty(Directory.EnumerateFileSystemEntries(target));
    }

    [LinuxFact]
    public void InvalidSocketPath_ReportsFailureInsteadOfSecondaryInstance()
    {
        Directory.CreateDirectory(_root);
        var path = Path.Combine(_root, new string('x', 120));
        Assert.ThrowsAny<Exception>(() => new UnixSingleInstanceCoordinator(path));
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
