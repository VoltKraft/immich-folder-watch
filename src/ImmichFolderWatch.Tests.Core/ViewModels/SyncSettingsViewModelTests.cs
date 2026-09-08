using ImmichFolderWatch.App.Shared.Models;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.ViewModels;

[Collection("Localization")]
public sealed class SyncSettingsViewModelTests
{
    [Fact]
    public void SyncStatus_ShowsInactiveAndCountsCompletedFilesAcrossBatches()
    {
        var status = new SyncStatusProvider();
        var vm = CreateViewModel(status);
        Assert.Equal("Inactive", vm.CurrentUploadText);

        status.ReportBatchStarted(3);
        status.ReportUploadStarted("first.jpg");
        Assert.Equal("Upload: first.jpg (0 of 3)", vm.CurrentUploadText);
        status.ReportUploadCompleted("first.jpg");
        status.ReportBatchCompleted();
        Assert.Equal("Inactive", vm.CurrentUploadText);

        status.ReportBatchStarted(2, continueProgress: true);
        status.ReportUploadStarted("second.jpg");
        Assert.Equal("Upload: second.jpg (1 of 3)", vm.CurrentUploadText);
        status.ReportUploadCompleted("second.jpg");
        status.ReportUploadSkipped();
        status.ReportBatchCompleted();
        Assert.Equal("Inactive", vm.CurrentUploadText);
        Assert.Equal(3, status.ProcessedFileCount);
        Assert.Equal(3, status.TotalFileCount);
    }

    [Fact]
    public void SyncStatus_RetainsFailureAfterCompletionAndSuccessfulServerCheck()
    {
        var status = new SyncStatusProvider();
        var vm = CreateViewModel(status);
        status.ReportBatchStarted(2);
        status.ReportUploadFailed("first.jpg", "Upload denied");
        status.ReportUploadCompleted("second.jpg");
        status.ReportBatchCompleted();
        status.ReportServerReachable(true);

        Assert.Equal("Sync error: Upload denied (2 of 2)", vm.CurrentUploadText);
        Assert.Equal(StatusTone.Error, vm.SyncStatusBadgeTone);

        status.ReportBatchStarted(1);
        status.ReportUploadStarted("first.jpg");
        Assert.Equal("Upload: first.jpg (0 of 1)", vm.CurrentUploadText);
        Assert.Null(status.LastSyncErrorMessage);
    }

    [Fact]
    public void SyncStatus_DownloadProgressAndEmptyErrorRemainVisible()
    {
        var status = new SyncStatusProvider();
        var vm = CreateViewModel(status);
        status.ReportPullStarted(2);
        status.ReportDownloadStarted("photo.jpg");
        Assert.Equal("Download: photo.jpg (0 of 2)", vm.CurrentUploadText);
        status.ReportDownloadCompleted("photo.jpg");
        status.ReportDownloadFailed("other.jpg", null);
        status.ReportPullCompleted();

        Assert.Equal("Sync error: other.jpg (2 of 2)", vm.CurrentUploadText);
    }

    [Fact]
    public void ServerFailure_DoesNotReplaceSyncErrorOrMarkInactiveSyncAsFailed()
    {
        var status = new SyncStatusProvider();
        var vm = CreateViewModel(status);
        status.ReportServerReachable(false, "Server offline");
        Assert.Equal("Inactive", vm.CurrentUploadText);
        Assert.Equal("Server offline", vm.ServerConnectionDetail);
        status.ReportBatchStarted(1);
        status.ReportUploadFailed("photo.jpg", "Upload denied");
        status.ReportBatchCompleted();
        Assert.Equal("Server offline", vm.ServerConnectionDetail);
        Assert.Equal("Sync error: Upload denied (1 of 1)", vm.CurrentUploadText);
    }

    [Theory]
    [InlineData(CheckState.NotChecked)]
    [InlineData(CheckState.Checking)]
    [InlineData(CheckState.Warning)]
    [InlineData(CheckState.Failed)]
    public void PermissionsSummary_IsNotOkWhenAnyPermissionIsNotPassed(CheckState state)
    {
        var vm = CreateViewModel(new SyncStatusProvider());
        vm.ApplyImmichCheckResult(new ImmichAccessCheckResult
        {
            PermissionsState = CheckState.Passed,
            PermissionResults =
            [
                new() { PermissionName = "asset.upload", State = CheckState.Passed },
                new() { PermissionName = "asset.read", State = state },
            ],
        });
        Assert.NotEqual(StatusTone.Success, vm.ImmichPermissionsStatusTone);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void PermissionsSummary_IsOkOnlyForNonEmptyPassedResults(bool hasResults)
    {
        var vm = CreateViewModel(new SyncStatusProvider());
        vm.ApplyImmichCheckResult(new ImmichAccessCheckResult
        {
            PermissionsState = CheckState.Passed,
            PermissionResults = hasResults
                ? [new() { PermissionName = "asset.upload", State = CheckState.Passed }]
                : [],
        });
        Assert.Equal(hasResults, vm.ImmichPermissionsStatusTone == StatusTone.Success);
    }

    [Fact]
    public void TransferOrder_DefaultsToNewestAndPreservesSelectionAcrossLoadSaveAndLanguageChange()
    {
        var localization = new LocalizationService();
        var vm = CreateViewModel(new SyncStatusProvider(), localization);
        Assert.Equal(TransferOrders.NewestFirst, vm.SelectedTransferOrder);
        vm.Load(new AppConfig { Watch = new WatchSettings { TransferOrder = TransferOrders.OldestFirst } });
        Assert.Equal(TransferOrders.OldestFirst, vm.SelectedTransferOrder);
        try
        {
            localization.SetLanguage(LocalizationService.LanguageGerman);
            Assert.Equal(TransferOrders.OldestFirst, vm.SelectedTransferOrder);
            Assert.Equal("Inaktiv", vm.CurrentUploadText);
            Assert.True(vm.TryCreateConfig(out var config, out var errors));
            Assert.Empty(errors);
            Assert.Equal(TransferOrders.OldestFirst, config.Watch.TransferOrder);
        }
        finally
        {
            localization.SetLanguage(LocalizationService.LanguageEnglish);
        }
    }

    private static MainWindowViewModel CreateViewModel(SyncStatusProvider status, LocalizationService? localization = null)
    {
        localization ??= new LocalizationService();
        localization.SetLanguage(LocalizationService.LanguageEnglish);
        return new MainWindowViewModel(status, new DisabledAutoStartManager(), localization,
            new ImmediateUiDispatcher(), new LinuxLoggingCapabilities());
    }

    private sealed class DisabledAutoStartManager : IAutoStartManager
    {
        public Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default) => Task.FromResult(false);
        public Task EnableAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task DisableAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class ImmediateUiDispatcher : IUiDispatcher
    {
        public bool IsOnUiThread => true;
        public void Post(Action action) => action();
    }
}
