using System.Reflection;
using System.Reflection.Emit;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.ViewModels;

public sealed class UpdateAvailabilityViewModelTests
{
    [Fact]
    public void ApplyUpdateInfo_SetsAndClearsLocalizedState()
    {
        var localization = new LocalizationService();
        localization.SetLanguage(LocalizationService.LanguageEnglish);
        var viewModel = CreateViewModel(localization, new ImmediateUiDispatcher());
        var update = new UpdateInfo(
            new Version(2, 8, 0),
            new Uri("https://github.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0"));

        viewModel.ApplyUpdateInfo(update);

        Assert.True(viewModel.IsUpdateAvailable);
        Assert.Equal("Update v2.8.0 available", viewModel.UpdateAvailableText);
        Assert.Equal(update.DownloadUri, viewModel.UpdateDownloadUri);

        viewModel.ApplyUpdateInfo(null);

        Assert.False(viewModel.IsUpdateAvailable);
        Assert.Empty(viewModel.UpdateAvailableText);
        Assert.Null(viewModel.UpdateDownloadUri);
    }

    [Fact]
    public void ApplyUpdateInfo_PostsAtomicChange_WhenCalledOffUiThread()
    {
        var dispatcher = new DeferredUiDispatcher();
        var viewModel = CreateViewModel(new LocalizationService(), dispatcher);
        var update = new UpdateInfo(
            new Version(2, 8, 0),
            new Uri("https://github.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0"));

        viewModel.ApplyUpdateInfo(update);

        Assert.False(viewModel.IsUpdateAvailable);
        Assert.NotNull(dispatcher.PostedAction);

        dispatcher.PostedAction();

        Assert.True(viewModel.IsUpdateAvailable);
        Assert.Equal(update.DownloadUri, viewModel.UpdateDownloadUri);
    }

    [Fact]
    public void LanguageChange_ReformatsAvailableUpdateText()
    {
        var localization = new LocalizationService();
        localization.SetLanguage(LocalizationService.LanguageEnglish);
        var viewModel = CreateViewModel(localization, new ImmediateUiDispatcher());
        viewModel.ApplyUpdateInfo(new UpdateInfo(
            new Version(2, 8, 0),
            new Uri("https://github.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0")));

        try
        {
            localization.SetLanguage(LocalizationService.LanguageGerman);

            Assert.Equal("Update v2.8.0 verfügbar", viewModel.UpdateAvailableText);
        }
        finally
        {
            localization.SetLanguage(LocalizationService.LanguageEnglish);
        }
    }

    [Fact]
    public void ProductVersionProvider_UsesInformationalVersionWithoutBuildMetadata()
    {
        var assembly = CreateDynamicAssembly(new Version(9, 8, 7, 6), "2.8.0+build.42");

        var version = ProductVersionProvider.GetProductVersion(assembly);

        Assert.Equal(new Version(2, 8, 0), version);
    }

    [Fact]
    public void ProductVersionProvider_FallsBackToThreeComponentAssemblyVersion()
    {
        var assembly = CreateDynamicAssembly(new Version(9, 8, 7, 6), "not-a-version");

        var version = ProductVersionProvider.GetProductVersion(assembly);

        Assert.Equal(new Version(9, 8, 7), version);
    }

    private static MainWindowViewModel CreateViewModel(
        LocalizationService localization,
        IUiDispatcher dispatcher)
    {
        return new MainWindowViewModel(
            new SyncStatusProvider(),
            new DisabledAutoStartManager(),
            localization,
            dispatcher,
            new LinuxLoggingCapabilities());
    }

    private static Assembly CreateDynamicAssembly(Version assemblyVersion, string informationalVersion)
    {
        var assemblyName = new AssemblyName($"ProductVersionProviderTests.{Guid.NewGuid():N}")
        {
            Version = assemblyVersion,
        };
        var assembly = AssemblyBuilder.DefineDynamicAssembly(assemblyName, AssemblyBuilderAccess.Run);
        var attributeConstructor = typeof(AssemblyInformationalVersionAttribute)
            .GetConstructor([typeof(string)])!;
        assembly.SetCustomAttribute(new CustomAttributeBuilder(attributeConstructor, [informationalVersion]));
        return assembly;
    }

    private sealed class DisabledAutoStartManager : IAutoStartManager
    {
        public Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default)
            => Task.FromResult(false);

        public Task EnableAsync(CancellationToken cancellationToken = default)
            => Task.CompletedTask;

        public Task DisableAsync(CancellationToken cancellationToken = default)
            => Task.CompletedTask;
    }

    private sealed class ImmediateUiDispatcher : IUiDispatcher
    {
        public bool IsOnUiThread => true;

        public void Post(Action action) => action();
    }

    private sealed class DeferredUiDispatcher : IUiDispatcher
    {
        public bool IsOnUiThread => false;

        public Action? PostedAction { get; private set; }

        public void Post(Action action) => PostedAction = action;
    }
}
