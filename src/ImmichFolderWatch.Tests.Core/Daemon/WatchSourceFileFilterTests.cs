using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Daemon;

public sealed class WatchSourceFileFilterTests
{
    [Fact]
    public void IsMatch_AllowsRootFilesWithConfiguredExtension()
    {
        var sourceRoot = Directory.CreateTempSubdirectory("ifw-filter-root-").FullName;

        try
        {
            var filter = new WatchSourceFileFilter(sourceRoot, [".jpg"]);

            Assert.True(filter.IsMatch(Path.Combine(sourceRoot, "Photo.JPG")));
        }
        finally
        {
            Directory.Delete(sourceRoot, recursive: true);
        }
    }

    [Fact]
    public void IsMatch_RejectsFilesInExcludedDirectoryAndNestedChildren()
    {
        var sourceRoot = Directory.CreateTempSubdirectory("ifw-filter-dir-").FullName;

        try
        {
            var filter = new WatchSourceFileFilter(sourceRoot, [".jpg"], excludeDirectories: ["private"]);

            Assert.False(filter.IsMatch(Path.Combine(sourceRoot, "private", "photo.jpg")));
            Assert.False(filter.IsMatch(Path.Combine(sourceRoot, "private", "nested", "photo.jpg")));
        }
        finally
        {
            Directory.Delete(sourceRoot, recursive: true);
        }
    }

    [Fact]
    public void IsMatch_RejectsFilesInGlobbedNestedDirectory()
    {
        var sourceRoot = Directory.CreateTempSubdirectory("ifw-filter-glob-dir-").FullName;

        try
        {
            var filter = new WatchSourceFileFilter(sourceRoot, [".jpg"], excludeDirectories: ["**/cache"]);

            Assert.False(filter.IsMatch(Path.Combine(sourceRoot, "cache", "photo.jpg")));
            Assert.False(filter.IsMatch(Path.Combine(sourceRoot, "imports", "cache", "photo.jpg")));
        }
        finally
        {
            Directory.Delete(sourceRoot, recursive: true);
        }
    }

    [Fact]
    public void IsMatch_RejectsExcludedFileNamesAndGlobPatterns()
    {
        var sourceRoot = Directory.CreateTempSubdirectory("ifw-filter-file-").FullName;

        try
        {
            var filter = new WatchSourceFileFilter(sourceRoot, [".jpg", ".tmp"], excludeFileNames: ["Thumbs.db", "*.tmp"]);

            Assert.False(filter.IsMatch(Path.Combine(sourceRoot, "Thumbs.db")));
            Assert.False(filter.IsMatch(Path.Combine(sourceRoot, "image.tmp")));
        }
        finally
        {
            Directory.Delete(sourceRoot, recursive: true);
        }
    }

    [Fact]
    public void IsMatch_UsesCaseInsensitiveMatching()
    {
        var sourceRoot = Directory.CreateTempSubdirectory("ifw-filter-case-").FullName;

        try
        {
            var filter = new WatchSourceFileFilter(
                sourceRoot,
                [".jpg"],
                excludeDirectories: ["**/TEMP"],
                excludeFileNames: ["IGNORE.*"]);

            Assert.False(filter.IsMatch(Path.Combine(sourceRoot, "Uploads", "Temp", "photo.jpg")));
            Assert.False(filter.IsMatch(Path.Combine(sourceRoot, "ignore.jpg")));
            Assert.True(filter.IsMatch(Path.Combine(sourceRoot, "keep.jpg")));
        }
        finally
        {
            Directory.Delete(sourceRoot, recursive: true);
        }
    }
}
