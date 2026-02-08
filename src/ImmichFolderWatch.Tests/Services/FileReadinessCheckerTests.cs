using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Services;

public sealed class FileReadinessCheckerTests
{
    [Fact]
    public async Task WaitUntilReadyAsync_ReturnsTrue_ForReadableFile()
    {
        var checker = new FileReadinessChecker();
        var filePath = Path.GetTempFileName();

        try
        {
            await File.WriteAllTextAsync(filePath, "data");

            var result = await checker.WaitUntilReadyAsync(
                filePath,
                TimeSpan.FromSeconds(2),
                CancellationToken.None);

            Assert.True(result);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task WaitUntilReadyAsync_ReturnsFalse_WhenTimeoutExpires()
    {
        var checker = new FileReadinessChecker();
        var filePath = Path.GetTempFileName();

        try
        {
            using var lockStream = new FileStream(
                filePath,
                FileMode.Open,
                FileAccess.ReadWrite,
                FileShare.None);

            var result = await checker.WaitUntilReadyAsync(
                filePath,
                TimeSpan.FromMilliseconds(300),
                CancellationToken.None);

            Assert.False(result);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact]
    public async Task WaitUntilReadyAsync_ReturnsTrue_AfterLockIsReleased()
    {
        var checker = new FileReadinessChecker();
        var filePath = Path.GetTempFileName();

        FileStream? lockStream = null;

        try
        {
            lockStream = new FileStream(
                filePath,
                FileMode.Open,
                FileAccess.ReadWrite,
                FileShare.None);

            var waitTask = checker.WaitUntilReadyAsync(
                filePath,
                TimeSpan.FromSeconds(3),
                CancellationToken.None);

            await Task.Delay(600);
            lockStream.Dispose();
            lockStream = null;

            var result = await waitTask;
            Assert.True(result);
        }
        finally
        {
            lockStream?.Dispose();
            File.Delete(filePath);
        }
    }
}
