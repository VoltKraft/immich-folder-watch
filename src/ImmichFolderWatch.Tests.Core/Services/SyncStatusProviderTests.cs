using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class SyncStatusProviderTests
{
    [Fact]
    public void BeginSyncSession_IgnoresLateHistoryFromPreviousWorker()
    {
        var status = new SyncStatusProvider();
        var previous = DateTimeOffset.UtcNow.AddDays(-1);
        var oldSession = status.BeginSyncSession();
        status.RestoreLastSyncCompleted(previous, oldSession);
        var currentSession = status.BeginSyncSession();
        Assert.Null(status.LastSyncCompletedUtc);
        status.RestoreLastSyncCompleted(previous, oldSession);
        status.ReportUploadCompleted("old-upload.jpg", DateTimeOffset.UtcNow, oldSession);
        status.ReportDownloadCompleted("old-download.jpg", DateTimeOffset.UtcNow, oldSession);
        Assert.Null(status.LastSyncCompletedUtc);
        status.RestoreLastSyncCompleted(previous.AddHours(-1), currentSession);
        Assert.Equal(previous.AddHours(-1), status.LastSyncCompletedUtc);
    }

    [Fact]
    public void RestoreLastSyncCompleted_ReplacesPriorAccountHistoryAndNotifiesObservers()
    {
        var status = new SyncStatusProvider();
        var previous = new DateTimeOffset(2026, 9, 8, 12, 0, 0, TimeSpan.FromHours(2));
        var notifications = new List<string?>();
        status.PropertyChanged += (_, args) => notifications.Add(args.PropertyName);

        status.RestoreLastSyncCompleted(previous);

        Assert.Equal(previous.ToUniversalTime(), status.LastSyncCompletedUtc);
        Assert.Equal(TimeSpan.Zero, status.LastSyncCompletedUtc!.Value.Offset);
        Assert.Contains(nameof(SyncStatusProvider.LastSyncCompletedUtc), notifications);
        status.RestoreLastSyncCompleted(null);
        Assert.Null(status.LastSyncCompletedUtc);
    }

    [Fact]
    public void SuccessfulTransfers_UsePersistedTimestampAndNeverRegressHistory()
    {
        var status = new SyncStatusProvider();
        var previous = new DateTimeOffset(2026, 9, 8, 10, 0, 0, TimeSpan.Zero);
        status.RestoreLastSyncCompleted(previous);
        status.ReportUploadCompleted("photo.jpg", previous.AddMinutes(1));
        Assert.Equal(previous.AddMinutes(1), status.LastSyncCompletedUtc);
        status.ReportDownloadCompleted("download.jpg", previous.AddMinutes(2));
        Assert.Equal(previous.AddMinutes(2), status.LastSyncCompletedUtc);
        status.ReportUploadCompleted("delayed.jpg", previous.AddMinutes(-1));
        Assert.Equal(previous.AddMinutes(2), status.LastSyncCompletedUtc);
    }

    [Fact]
    public void FailedSkippedAndEmptyOperations_DoNotChangeRestoredHistory()
    {
        var status = new SyncStatusProvider();
        var previous = DateTimeOffset.UtcNow.AddDays(-1);
        status.RestoreLastSyncCompleted(previous);
        status.ReportBatchStarted(2);
        status.ReportUploadSkipped();
        status.ReportUploadFailed("upload.jpg", "Upload denied");
        status.ReportBatchCompleted();
        status.ReportPullCycleStarted();
        status.ReportPullCycleCompleted(completed: true);
        status.ReportDownloadFailed("download.jpg", "Download denied");
        status.ReportServerReachable(true);
        Assert.Equal(previous, status.LastSyncCompletedUtc);
    }

    [Fact]
    public void UploadProgress_ResumesAcrossBatchesWithoutUsingInterveningPullCounters()
    {
        var provider = new SyncStatusProvider();
        provider.ReportBatchStarted(3);
        provider.ReportUploadFailed("failed.jpg", "Upload denied");
        provider.ReportBatchCompleted();
        provider.ReportPullCycleStarted();
        provider.ReportPullStarted(2);
        provider.ReportDownloadCompleted("remote-one.jpg");
        provider.ReportDownloadCompleted("remote-two.jpg");
        provider.ReportPullCompleted();
        provider.ReportPullCycleCompleted(completed: true);

        provider.ReportBatchStarted(2, continueProgress: true);

        Assert.Equal(1, provider.ProcessedFileCount);
        Assert.Equal(3, provider.TotalFileCount);
        Assert.Equal("Upload denied", provider.LastSyncErrorMessage);
        provider.ReportUploadCompleted("second.jpg");
        provider.ReportUploadSkipped();
        Assert.Equal(2, provider.ProcessedInCurrentBatch);
        provider.ReportBatchCompleted();
        Assert.Equal(3, provider.ProcessedFileCount);
        Assert.Equal(3, provider.TotalFileCount);
    }

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
    [Fact]
    public void ReportUploadFailed_AdvancesProcessedBatchCount()
    {
        var provider = new SyncStatusProvider();
        provider.ReportBatchStarted(2);
        provider.ReportUploadStarted("failed.jpg");

        provider.ReportUploadFailed("failed.jpg", "unsupported format");

        Assert.Equal(1, provider.ProcessedInCurrentBatch);
        Assert.Equal(0, provider.UploadedInCurrentBatch);
        Assert.Null(provider.CurrentlyUploadingFile);
    }

    [Fact]
    public void ReportUploadSkipped_AdvancesProcessedBatchCount()
    {
        var provider = new SyncStatusProvider();
        provider.ReportBatchStarted(2);

        provider.ReportUploadSkipped();

        Assert.Equal(1, provider.ProcessedInCurrentBatch);
        Assert.Equal(0, provider.UploadedInCurrentBatch);
    }
}
