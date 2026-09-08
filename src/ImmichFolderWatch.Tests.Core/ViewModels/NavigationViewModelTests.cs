using ImmichFolderWatch.App.Shared.Models;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.ViewModels;

[Collection("Localization")]
public sealed class NavigationViewModelTests
{
    [Fact]
    public void AddSource_SelectsNewDraftAndOpensFolders()
    {
        var vm = CreateViewModel();
        Assert.True(vm.IsOverviewSelected);
        Assert.Same(vm.Sources[0], vm.SelectedSource);

        vm.AddSource();

        Assert.Same(vm.Sources[1], vm.SelectedSource);
        Assert.True(vm.IsFoldersSelected);
        Assert.True(vm.HasSelectedSource);
    }

    [Fact]
    public void RemoveSource_SelectsNextThenPreviousAndSupportsEmptyList()
    {
        var vm = CreateViewModel();
        var first = vm.SelectedSource!;
        vm.AddSource();
        var second = vm.SelectedSource!;
        vm.AddSource();
        var third = vm.SelectedSource!;
        vm.SelectedSource = second;

        vm.Sources.Remove(second);
        Assert.Same(third, vm.SelectedSource);
        vm.Sources.Remove(third);
        Assert.Same(first, vm.SelectedSource);
        vm.Sources.Remove(first);
        Assert.Null(vm.SelectedSource);
        Assert.False(vm.HasSelectedSource);
        vm.AddSource();
        Assert.Same(Assert.Single(vm.Sources), vm.SelectedSource);
    }

    [Fact]
    public void RemoveUnselectedSource_PreservesCurrentSelection()
    {
        var vm = CreateViewModel();
        var first = vm.SelectedSource!;
        vm.AddSource();
        var selected = vm.SelectedSource;
        vm.Sources.Remove(first);
        Assert.Same(selected, vm.SelectedSource);
    }

    [Fact]
    public void Navigation_PreservesAllSourceEditsAndGlobalSettingsWhenCreatingConfig()
    {
        var vm = CreateViewModel();
        vm.ImmichServerApiUrl = "https://immich.example.com/api";
        vm.ImmichApiKey = "IMMICH_API_KEY";
        vm.SelectedTransferOrder = TransferOrders.OldestFirst;
        vm.BatchIntervalSeconds = "12";
        vm.MaxBatchSize = "17";
        vm.FileReadyTimeoutSeconds = "42";
        vm.RetryMaxAttempts = "7";
        vm.RetryBaseDelayMilliseconds = "750";
        vm.LoggingLevel = "Debug";
        vm.LoggingTarget = LogTargets.File;
        vm.LogDirectory = Path.Combine(Path.GetTempPath(), "ifw-navigation-tests", "logs");
        var first = vm.SelectedSource!;
        first.Path = "/photos/first";
        first.AlbumName = "Custom album";
        first.SyncMode = WatchSourceSyncModes.UploadAll;
        first.IncludeSubdirectories = true;
        first.DeleteAfterUpload = true;
        first.ExtensionsText = ".jpg\n.png";
        first.ExcludeDirectoriesText = ".cache\nprivate";
        first.ExcludeFileNamesText = "*.tmp\nThumbs.db";
        vm.AddSource();
        var second = vm.SelectedSource!;
        second.SetPortalPath("/run/user/1000/doc/example/photos", "/home/example/Pictures");
        second.AlbumName = string.Empty;
        second.SyncMode = WatchSourceSyncModes.Sync;
        vm.SelectedSectionIndex = 2;
        vm.SelectedSectionIndex = 3;
        vm.SelectedSectionIndex = 1;
        vm.SelectedSource = first;

        Assert.Equal("Custom album", vm.SelectedSource.AlbumName);
        Assert.True(vm.TryCreateConfig(out var config, out var errors), string.Join(Environment.NewLine, errors));
        Assert.Empty(errors);
        Assert.Equal(2, config.Watch.Sources.Count);
        var saved = config.Watch.Sources[0];
        Assert.Equal(first.Path, saved.Path);
        Assert.Equal(first.AlbumName, saved.AlbumName);
        Assert.Equal(first.SyncMode, saved.SyncMode);
        Assert.True(saved.IncludeSubdirectories);
        Assert.True(saved.DeleteAfterUpload);
        Assert.Equal(new[] { ".jpg", ".png" }, saved.Extensions);
        Assert.Equal(new[] { ".cache", "private" }, saved.ExcludeDirectories);
        Assert.Equal(new[] { "*.tmp", "Thumbs.db" }, saved.ExcludeFileNames);
        Assert.Equal(second.Path, config.Watch.Sources[1].Path);
        Assert.NotEqual(second.DisplayPath, config.Watch.Sources[1].Path);
        Assert.Equal(string.Empty, config.Watch.Sources[1].AlbumName);
        Assert.Equal(WatchSourceSyncModes.Sync, config.Watch.Sources[1].SyncMode);
        Assert.Equal(TransferOrders.OldestFirst, config.Watch.TransferOrder);
        Assert.Equal(12, config.Watch.BatchIntervalSeconds);
        Assert.Equal(17, config.Watch.MaxBatchSize);
        Assert.Equal(42, config.Watch.FileReadyTimeoutSeconds);
        Assert.Equal(7, config.Retry.MaxAttempts);
        Assert.Equal(750, config.Retry.BaseDelayMilliseconds);
        Assert.Equal("Debug", config.Logging.Level);
        Assert.Equal(LogTargets.File, config.Logging.Target);
        Assert.Equal(vm.LogDirectory, config.Logging.LogDirectory);
        Assert.Equal(vm.ImmichServerApiUrl, config.Immich.ServerApiUrl);
        Assert.Equal(vm.ImmichApiKey, config.Immich.ApiKey);
    }

    [Fact]
    public void Load_RestoresSelectedPathAndPageAfterApply()
    {
        var vm = CreateViewModel();
        vm.SelectedSource!.Path = "/photos/first";
        vm.AddSource();
        vm.SelectedSource!.Path = "/photos/second";
        vm.SelectedSectionIndex = 3;
        Assert.True(vm.TryCreateConfig(out var config, out _));
        var previous = vm.SelectedSource;

        vm.Load(config);

        Assert.NotSame(previous, vm.SelectedSource);
        Assert.Equal("/photos/second", vm.SelectedSource!.Path);
        Assert.True(vm.IsSettingsSelected);
        vm.Load(new AppConfig());
        Assert.Same(Assert.Single(vm.Sources), vm.SelectedSource);
        Assert.True(vm.IsSettingsSelected);
    }

    [Fact]
    public void LanguageChange_RefreshesNavigationAndEmptyFolderNameWithoutChangingDraft()
    {
        var localization = new LocalizationService();
        var vm = CreateViewModel(localization);
        var source = vm.SelectedSource!;
        source.SyncMode = WatchSourceSyncModes.Sync;
        var changed = new List<string?>();
        source.PropertyChanged += (_, e) => changed.Add(e.PropertyName);
        var proxy = new LocalizationProxy(localization);
        try
        {
            localization.SetLanguage("de");
            Assert.Equal("Neuer Ordner", source.DisplayName);
            Assert.Equal("Übersicht", proxy.UI_Overview);
            Assert.Contains(nameof(WatchSourceItem.DisplayName), changed);
            Assert.Same(source, vm.SelectedSource);
            Assert.Equal(WatchSourceSyncModes.Sync, source.SelectedSyncModeOption!.Code);
        }
        finally
        {
            localization.SetLanguage("en");
        }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    public void Navigation_ExposesExactlyOneSectionAndRejectsInvalidSelection(int section)
    {
        var vm = CreateViewModel();
        vm.SelectedSectionIndex = section;
        Assert.Single(new[] { vm.IsOverviewSelected, vm.IsFoldersSelected, vm.IsConnectionSelected, vm.IsSettingsSelected }.Where(value => value));
        vm.SelectedSectionIndex = -1;
        vm.SelectedSectionIndex = 4;
        Assert.Equal(section, vm.SelectedSectionIndex);
        var selected = vm.SelectedSource;
        vm.SelectedSource = new WatchSourceItem();
        Assert.Same(selected, vm.SelectedSource);
    }

    private static MainWindowViewModel CreateViewModel(LocalizationService? localization = null)
    {
        localization ??= new LocalizationService();
        localization.SetLanguage("en");
        return new MainWindowViewModel(new SyncStatusProvider(), new DisabledAutoStartManager(), localization,
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
