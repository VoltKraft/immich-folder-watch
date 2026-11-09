using ImmichFolderWatch.Core.Platform;
using System.Runtime.Versioning;

namespace ImmichFolderWatch.Tests.Core.Platform;

[SupportedOSPlatform("linux")]
public sealed class LinuxPrivateDirectoryTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), $"ifw-private-{Guid.NewGuid():N}");

    [Fact]
    public async Task Save_RepairsPermissiveDirectoryAndReplacesPermissiveFileWithPrivateFile()
    {
        if (!OperatingSystem.IsLinux()) return;
        Directory.CreateDirectory(_root);
        File.SetUnixFileMode(_root, (UnixFileMode)0x1ff);
        var path = Path.Combine(_root, "config.yaml");
        await File.WriteAllTextAsync(path, "old");
        File.SetUnixFileMode(path, (UnixFileMode)0x1b6);

        using var directory = LinuxPrivateDirectory.Open(_root);
        await directory.WriteTextAtomicallyAsync("config.yaml", "synthetic test data", CancellationToken.None);

        Assert.Equal((UnixFileMode)0x1c0, File.GetUnixFileMode(_root));
        Assert.Equal((UnixFileMode)0x180, File.GetUnixFileMode(path));
        Assert.Equal("synthetic test data", await File.ReadAllTextAsync(path));
        Assert.Single(Directory.EnumerateFiles(_root));
    }

    [Fact]
    public async Task Save_DoesNotFollowExistingConfigSymlink()
    {
        if (!OperatingSystem.IsLinux()) return;
        Directory.CreateDirectory(_root);
        var target = Path.Combine(_root, "target");
        await File.WriteAllTextAsync(target, "unchanged");
        File.CreateSymbolicLink(Path.Combine(_root, "config.yaml"), target);

        using var directory = LinuxPrivateDirectory.Open(_root);
        await Assert.ThrowsAsync<IOException>(() => directory.WriteTextAtomicallyAsync("config.yaml", "new", CancellationToken.None));
        Assert.Equal("unchanged", await File.ReadAllTextAsync(target));
    }

    [Fact]
    public void Open_RejectsLinkedDirectoryWithoutChangingTargetMode()
    {
        if (!OperatingSystem.IsLinux()) return;
        Directory.CreateDirectory(_root);
        var target = Path.Combine(_root, "target");
        Directory.CreateDirectory(target);
        File.SetUnixFileMode(target, (UnixFileMode)0x1ed);
        var link = Path.Combine(_root, "link");
        Directory.CreateSymbolicLink(link, target);

        Assert.Throws<IOException>(() => LinuxPrivateDirectory.Open(link));
        Assert.Equal((UnixFileMode)0x1ed, File.GetUnixFileMode(target));
    }

    [Fact]
    public void Open_RejectsNonStickyWritableAncestor()
    {
        if (!OperatingSystem.IsLinux()) return;
        Directory.CreateDirectory(_root);
        File.SetUnixFileMode(_root, (UnixFileMode)0x1ff);
        Assert.Throws<IOException>(() => LinuxPrivateDirectory.Open(Path.Combine(_root, "private")));
        Assert.False(Directory.Exists(Path.Combine(_root, "private")));
    }

    [Fact]
    public async Task Save_UsesOpenedDirectoryEvenWhenPathIsReplaced()
    {
        if (!OperatingSystem.IsLinux()) return;
        Directory.CreateDirectory(_root);
        var original = Path.Combine(_root, "original");
        var moved = Path.Combine(_root, "moved");
        var outside = Path.Combine(_root, "outside");
        Directory.CreateDirectory(outside);
        using var directory = LinuxPrivateDirectory.Open(original);
        Directory.Move(original, moved);
        Directory.CreateSymbolicLink(original, outside);

        await directory.WriteTextAtomicallyAsync("config.yaml", "synthetic test data", CancellationToken.None);

        Assert.Equal("synthetic test data", await File.ReadAllTextAsync(Path.Combine(moved, "config.yaml")));
        Assert.Empty(Directory.EnumerateFileSystemEntries(outside));
    }

    [Fact]
    public async Task Save_CanceledWritePreservesExistingFileAndRemovesTemporaryFile()
    {
        if (!OperatingSystem.IsLinux()) return;
        using var directory = LinuxPrivateDirectory.Open(_root);
        var path = Path.Combine(_root, "config.yaml");
        await File.WriteAllTextAsync(path, "old");
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => directory.WriteTextAtomicallyAsync("config.yaml", "new", cancellation.Token));

        Assert.Equal("old", await File.ReadAllTextAsync(path));
        Assert.Single(Directory.EnumerateFiles(_root));
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
