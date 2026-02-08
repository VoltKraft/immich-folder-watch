using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Services;

public sealed class UploadBatchQueueTests
{
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
