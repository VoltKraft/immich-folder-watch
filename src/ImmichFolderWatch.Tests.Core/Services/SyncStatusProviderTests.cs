using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class SyncStatusProviderTests
{
    [Fact]
    public void PullCycle_RetainsEarlierAlbumFailureAndAccumulatesFileProgress()
    {
        var status = new SyncStatusProvider();
        status.ReportPullCycleStarted();
        status.ReportPullStarted(1);
        status.ReportDownloadFailed("first.jpg", "Download denied");
        status.ReportPullCompleted();
        status.ReportPullStarted(1);
        status.ReportDownloadCompleted("second.jpg");
        status.ReportPullCompleted();
        status.ReportPullCycleCompleted(completed: true);

        Assert.Equal("Download denied", status.LastSyncErrorMessage);
        Assert.Equal(2, status.ProcessedFileCount);
        Assert.Equal(2, status.TotalFileCount);
    }

    [Fact]
    public void PullCycle_ListingFailureSurvivesLaterSuccessfulAlbum()
    {
        var status = new SyncStatusProvider();
        status.ReportPullCycleStarted();
        status.ReportSyncFailed("Listing denied");
        status.ReportPullStarted(1);
        status.ReportDownloadCompleted("photo.jpg");
        status.ReportPullCompleted();
        status.ReportPullCycleCompleted(completed: true);

        Assert.Equal("Listing denied", status.LastSyncErrorMessage);
        Assert.Equal(1, status.ProcessedFileCount);
        Assert.Equal(1, status.TotalFileCount);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void PullCycle_OnlyCompleteSuccessfulEmptyScanClearsPreviousPullError(bool completed)
    {
        var status = new SyncStatusProvider();
        status.ReportPullCycleStarted();
        status.ReportPullStarted(1);
        status.ReportDownloadFailed("photo.jpg", "Download denied");
        status.ReportPullCompleted();
        status.ReportPullCycleCompleted(completed: true);
        status.ReportPullCycleStarted();
        status.ReportPullCycleCompleted(completed);

        Assert.Equal(completed ? null : "Download denied", status.LastSyncErrorMessage);
        Assert.Equal(1, status.ProcessedFileCount);
        Assert.Equal(1, status.TotalFileCount);
    }

    [Fact]
    public void PullCycle_EmptySuccessfulScanPreservesUploadFailureAndProgress()
    {
        var status = new SyncStatusProvider();
        status.ReportBatchStarted(1);
        status.ReportUploadFailed("photo.jpg", "Upload denied");
        status.ReportBatchCompleted();
        status.ReportPullCycleStarted();
        status.ReportPullCycleCompleted(completed: true);

        Assert.Equal("Upload denied", status.LastSyncErrorMessage);
        Assert.Equal(1, status.ProcessedFileCount);
        Assert.Equal(1, status.TotalFileCount);
    }
}
