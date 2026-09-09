using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class DownloadedFileTimestampsTests
{
    [Fact]
    public void GetDesired_RequiresOriginalCreationTimeEvenWhenTransferOrderingTimeExists()
    {
        var asset = new AlbumAssetSummary("asset", "photo.jpg", DateTimeOffset.UtcNow);

        Assert.Null(DownloadedFileTimestamps.GetDesired(asset));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void GetDesired_NormalizesOffsetsAndUsesPlatformTimestampPolicy(bool hasModifiedTime)
    {
        var created = new DateTimeOffset(2020, 2, 3, 14, 15, 16, TimeSpan.FromHours(2));
        DateTimeOffset? modified = hasModifiedTime ? created.AddDays(5) : null;
        var asset = new AlbumAssetSummary("asset", "photo.jpg", modified, created);

        var desired = Assert.IsType<DownloadedFileTimestampValues>(DownloadedFileTimestamps.GetDesired(asset));

        Assert.Equal(created.UtcDateTime, desired.CreationTimeUtc.UtcDateTime);
        Assert.Equal(TimeSpan.Zero, desired.CreationTimeUtc.Offset);
        Assert.Equal(TimeSpan.Zero, desired.LastWriteTimeUtc.Offset);
        Assert.Equal((OperatingSystem.IsWindows() ? modified ?? created : created).UtcDateTime,
            desired.LastWriteTimeUtc.UtcDateTime);
    }

    [Fact]
    public void Apply_UpdatesRealFileDatesWithoutChangingItsContents()
    {
        var directory = Path.Combine(Path.GetTempPath(), "ifw-timestamp-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var path = Path.Combine(directory, "photo.jpg");
            byte[] contents = [1, 3, 5, 7, 9];
            File.WriteAllBytes(path, contents);
            var created = new DateTimeOffset(2020, 2, 3, 14, 15, 16, TimeSpan.FromHours(2));
            var modified = created.AddDays(5);
            var desired = DownloadedFileTimestamps.GetDesired(new AlbumAssetSummary("asset", "photo.jpg", modified, created))!;

            DownloadedFileTimestamps.Apply(path, desired);

            Assert.Equal(desired.LastWriteTimeUtc.UtcDateTime, File.GetLastWriteTimeUtc(path));
            if (OperatingSystem.IsWindows())
            {
                Assert.Equal(desired.CreationTimeUtc.UtcDateTime, File.GetCreationTimeUtc(path));
            }
            Assert.Equal(contents, File.ReadAllBytes(path));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public void Apply_MissingFilePropagatesFailureWithoutCreatingIt()
    {
        var path = Path.Combine(Path.GetTempPath(), "ifw-missing-timestamp-" + Guid.NewGuid().ToString("N"));
        var timestamp = new DateTimeOffset(2020, 1, 1, 0, 0, 0, TimeSpan.Zero);

        Assert.ThrowsAny<IOException>(() => DownloadedFileTimestamps.Apply(path,
            new DownloadedFileTimestampValues(timestamp, timestamp)));

        Assert.False(File.Exists(path));
    }
}
