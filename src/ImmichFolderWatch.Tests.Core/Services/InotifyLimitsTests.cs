using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class InotifyLimitsTests
{
    [Fact]
    public void GetMaxUserWatches_ReadsValueFromCustomPath()
    {
        if (!OperatingSystem.IsLinux())
        {
            Assert.Null(InotifyLimits.GetMaxUserWatches("/tmp/never-exists.txt"));
            return;
        }

        var temp = Path.Combine(Path.GetTempPath(), $"max-watches-{Guid.NewGuid():N}");
        File.WriteAllText(temp, "524288\n");
        try
        {
            var value = InotifyLimits.GetMaxUserWatches(temp);
            Assert.Equal(524288L, value);
        }
        finally
        {
            File.Delete(temp);
        }
    }

    [Fact]
    public void GetMaxUserWatches_ReturnsNull_OnMissingFile()
    {
        Assert.Null(InotifyLimits.GetMaxUserWatches("/tmp/definitely-not-here-9b2f.txt"));
    }

    [Fact]
    public void GetMaxUserWatches_ReturnsNull_OnUnparseableContent()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        var temp = Path.Combine(Path.GetTempPath(), $"max-watches-{Guid.NewGuid():N}");
        File.WriteAllText(temp, "not-a-number");
        try
        {
            Assert.Null(InotifyLimits.GetMaxUserWatches(temp));
        }
        finally
        {
            File.Delete(temp);
        }
    }

    [Fact]
    public void CountWatchedDirectories_ReturnsZero_ForMissingPath()
    {
        Assert.Equal(0, InotifyLimits.CountWatchedDirectories("/tmp/missing-dir-c4e1", true));
    }

    [Fact]
    public void CountWatchedDirectories_ReturnsOne_WhenNotRecursive()
    {
        var dir = Directory.CreateTempSubdirectory("inotify-tests-");
        try
        {
            Directory.CreateDirectory(Path.Combine(dir.FullName, "child"));
            Assert.Equal(1, InotifyLimits.CountWatchedDirectories(dir.FullName, includeSubdirectories: false));
        }
        finally
        {
            Directory.Delete(dir.FullName, recursive: true);
        }
    }

    [Fact]
    public void CountWatchedDirectories_CountsRoot_PlusAllSubdirectoriesRecursively()
    {
        var dir = Directory.CreateTempSubdirectory("inotify-tests-");
        try
        {
            Directory.CreateDirectory(Path.Combine(dir.FullName, "a"));
            Directory.CreateDirectory(Path.Combine(dir.FullName, "a", "b"));
            Directory.CreateDirectory(Path.Combine(dir.FullName, "c"));

            Assert.Equal(4, InotifyLimits.CountWatchedDirectories(dir.FullName, includeSubdirectories: true));
        }
        finally
        {
            Directory.Delete(dir.FullName, recursive: true);
        }
    }
}
