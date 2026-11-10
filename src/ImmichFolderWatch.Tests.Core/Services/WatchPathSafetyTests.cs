using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class WatchPathSafetyTests
{
    [Fact]
    public void LinkedFilesAndDirectoriesAreRejectedAndNotEnumerated()
    {
        if (OperatingSystem.IsWindows()) return; // Windows symlink privilege is not assumed.
        var root = Directory.CreateTempSubdirectory("ifw-path-security-");
        var outside = Directory.CreateTempSubdirectory("ifw-path-outside-");
        try
        {
            var target = Path.Combine(outside.FullName, "photo.jpg");
            File.WriteAllText(target, "outside");
            var fileLink = Path.Combine(root.FullName, "linked.jpg");
            File.CreateSymbolicLink(fileLink, target);
            var dirLink = Path.Combine(root.FullName, "linked-dir");
            Directory.CreateSymbolicLink(dirLink, outside.FullName);
            var dangling = Path.Combine(root.FullName, "dangling.jpg");
            File.CreateSymbolicLink(dangling, Path.Combine(outside.FullName, "missing.jpg"));
            Assert.False(WatchPathSafety.IsSafePath(root.FullName, fileLink));
            Assert.False(WatchPathSafety.IsSafePath(root.FullName, Path.Combine(dirLink, "photo.jpg")));
            Assert.False(WatchPathSafety.IsSafePath(root.FullName, Path.Combine(dirLink, "new.jpg"), true));
            Assert.False(WatchPathSafety.IsSafePath(root.FullName, dangling, true));
            Assert.Empty(Directory.EnumerateFiles(root.FullName, "*", WatchPathSafety.EnumerationOptions(true)));
            Assert.Equal("outside", File.ReadAllText(target));
        }
        finally
        {
            root.Delete(true);
            outside.Delete(true);
        }
    }

    [Fact]
    public void NormalNestedPathsAreAllowedButSiblingRootsAreRejected()
    {
        var root = Directory.CreateTempSubdirectory("ifw-path-security-");
        try
        {
            var child = Directory.CreateDirectory(Path.Combine(root.FullName, "nested"));
            var file = Path.Combine(child.FullName, "photo.jpg");
            File.WriteAllText(file, "inside");
            Assert.True(WatchPathSafety.IsSafePath(root.FullName, file));
            Assert.True(WatchPathSafety.IsSafePath(root.FullName, Path.Combine(child.FullName, "new.jpg"), true));
            Assert.False(WatchPathSafety.IsSafePath(root.FullName, root.FullName + "-sibling/photo.jpg", true));
            Assert.False(WatchPathSafety.IsSafePath(root.FullName, Path.Combine(root.FullName, "..", "outside.jpg"), true));
        }
        finally { root.Delete(true); }
    }
}
