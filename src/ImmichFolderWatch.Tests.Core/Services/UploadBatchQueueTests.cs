using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class UploadBatchQueueTests
{
    [Theory]
    [InlineData(TransferOrders.NewestFirst, "new.jpg", "old.jpg")]
    [InlineData(TransferOrders.OldestFirst, "old.jpg", "new.jpg")]
    public void DequeueBatch_OrdersEntireQueueBeforeApplyingBatchSize(string order, string first, string second)
    {
        var directory = Directory.CreateTempSubdirectory("ifw-order-");
        try
        {
            var oldPath = Path.Combine(directory.FullName, "old.jpg");
            var newPath = Path.Combine(directory.FullName, "new.jpg");
            File.WriteAllText(oldPath, "old");
            File.WriteAllText(newPath, "new");
            File.SetLastWriteTimeUtc(oldPath, new DateTime(2025, 1, 1, 0, 0, 0, DateTimeKind.Utc));
            File.SetLastWriteTimeUtc(newPath, new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc));
            var queue = new UploadBatchQueue();
            queue.TryEnqueue(new UploadAssetRequest(Path.Combine(directory.FullName, "missing.jpg"), "Unknown"));
            queue.TryEnqueue(new UploadAssetRequest(oldPath, "Album A"));
            queue.TryEnqueue(new UploadAssetRequest(newPath, "Album B"));

            Assert.Equal(first, Path.GetFileName(Assert.Single(queue.DequeueBatch(1, order)).FilePath));
            Assert.Equal(second, Path.GetFileName(Assert.Single(queue.DequeueBatch(1, order)).FilePath));
            Assert.Equal("missing.jpg", Path.GetFileName(Assert.Single(queue.DequeueBatch(1, order)).FilePath));
            Assert.Equal(0, queue.Count);
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }

    [Fact]
    public void TryEnqueue_DeduplicatesByPathWhileQueued()
    {
        var queue = new UploadBatchQueue();
        var path = Path.Combine(Path.GetTempPath(), "ifw-example.png");
        var request = new UploadAssetRequest(path, "Screenshots");

        var first = queue.TryEnqueue(request);
        var second = queue.TryEnqueue(request);

        Assert.True(first);
        Assert.False(second);
        Assert.Equal(1, queue.Count);
    }

    [Fact]
    public void DequeueBatch_RespectsMaxBatchSizeAndOrder()
    {
        var queue = new UploadBatchQueue();
        var firstPath = Path.Combine(Path.GetTempPath(), "ifw-a.png");
        var secondPath = Path.Combine(Path.GetTempPath(), "ifw-b.png");
        var thirdPath = Path.Combine(Path.GetTempPath(), "ifw-c.png");

        queue.TryEnqueue(new UploadAssetRequest(firstPath, "Album A"));
        queue.TryEnqueue(new UploadAssetRequest(secondPath, "Album B"));
        queue.TryEnqueue(new UploadAssetRequest(thirdPath, "Album C"));

        var batch = queue.DequeueBatch(2);

        Assert.Equal(2, batch.Count);
        Assert.Equal(Path.GetFullPath(firstPath), batch[0].FilePath);
        Assert.Equal(Path.GetFullPath(secondPath), batch[1].FilePath);
        Assert.Equal(1, queue.Count);
    }

    [Fact]
    public void TryEnqueue_AllowsSamePathAgainAfterDequeue()
    {
        var queue = new UploadBatchQueue();
        var path = Path.Combine(Path.GetTempPath(), "ifw-retry.png");
        var request = new UploadAssetRequest(path, "Screenshots");

        Assert.True(queue.TryEnqueue(request));
        var firstBatch = queue.DequeueBatch(10);
        Assert.Single(firstBatch);

        Assert.True(queue.TryEnqueue(request));
    }
}
