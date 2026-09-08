using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.Services;

public sealed class SyncStatusProviderTests
{
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
