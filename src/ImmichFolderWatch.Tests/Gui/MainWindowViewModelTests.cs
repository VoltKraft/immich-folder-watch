using ImmichFolderWatch.App.Services;
using ImmichFolderWatch.App.Shared.Models;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using System.Reflection;
using System.Reflection.Emit;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;
using SharedProductVersionProvider = ImmichFolderWatch.App.Shared.Services.ProductVersionProvider;

namespace ImmichFolderWatch.Tests.Gui;

public sealed class MainWindowViewModelTests
{
    private static readonly string[] ExpectedDefaultImageExtensions =
    {
        ".3fr",
        ".3gp",
        ".3gpp",
        ".ari",
        ".arw",
        ".avi",
        ".avif",
        ".bmp",
        ".cap",
        ".cin",
        ".cr2",
        ".cr3",
        ".crw",
        ".dcr",
        ".dng",
        ".erf",
        ".fff",
        ".flv",
        ".gif",
        ".heic",
        ".heif",
        ".hif",
        ".iiq",
        ".insp",
        ".insv",
        ".jp2",
        ".jpe",
        ".jpeg",
        ".jpg",
        ".jxl",
        ".k25",
        ".kdc",
        ".m2t",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpe",
        ".mpeg",
        ".mpg",
        ".mrw",
        ".mts",
        ".nef",
        ".nrw",
        ".orf",
        ".ori",
        ".pef",
        ".png",
        ".psd",
        ".raf",
        ".raw",
        ".rw2",
        ".rwl",
        ".sr2",
        ".srf",
        ".srw",
        ".svg",
        ".tif",
        ".tiff",
        ".vob",
        ".webm",
        ".webp",
        ".wmv",
        ".x3f",
    };

    private static MainWindowViewModel CreateViewModel(
        LocalizationService? localizationService = null,
        IUiDispatcher? uiDispatcher = null)
    {
        return new MainWindowViewModel(
            new SyncStatusProvider(),
            new AutostartManager(),
            localizationService ?? LocalizationService.Instance,
            uiDispatcher ?? new SyncTestUiDispatcher(),
            new WindowsLoggingCapabilities());
    }

    private sealed class SyncTestUiDispatcher : IUiDispatcher
    {
        public bool IsOnUiThread => true;

        public void Post(Action action)
        {
            ArgumentNullException.ThrowIfNull(action);
            action();
        }
    }

    private sealed class DeferredTestUiDispatcher : IUiDispatcher
    {
        public bool IsOnUiThread => false;

        public Action? PostedAction { get; private set; }

        public void Post(Action action)
        {
            ArgumentNullException.ThrowIfNull(action);
            PostedAction = action;
        }
    }

    [Fact]
    public void ApplyUpdateInfo_SetsLocalizedBindableStateAtomically()
    {
        var localizationService = new LocalizationService();
        localizationService.SetLanguage(LocalizationService.LanguageEnglish);
        var viewModel = CreateViewModel(localizationService);
        var changedProperties = new List<string?>();
        var stateWasConsistentDuringNotifications = true;
        var downloadUri = new Uri("https://github.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0");
        viewModel.PropertyChanged += (_, args) =>
        {
            changedProperties.Add(args.PropertyName);
            stateWasConsistentDuringNotifications &= viewModel.IsUpdateAvailable
                && viewModel.UpdateAvailableText == "Update v2.8.0 available"
                && viewModel.UpdateDownloadUri == downloadUri;
        };

        viewModel.ApplyUpdateInfo(new UpdateInfo(new Version(2, 8, 0), downloadUri));

        Assert.True(viewModel.IsUpdateAvailable);
        Assert.Equal("Update v2.8.0 available", viewModel.UpdateAvailableText);
        Assert.Equal(downloadUri, viewModel.UpdateDownloadUri);
        Assert.True(stateWasConsistentDuringNotifications);
        Assert.Equal(
            [nameof(MainWindowViewModel.IsUpdateAvailable), nameof(MainWindowViewModel.UpdateAvailableText), nameof(MainWindowViewModel.UpdateDownloadUri)],
            changedProperties);
    }

    [Fact]
    public void ApplyUpdateInfo_WithNull_ClearsBindableState()
    {
        var localizationService = new LocalizationService();
        localizationService.SetLanguage(LocalizationService.LanguageEnglish);
        var viewModel = CreateViewModel(localizationService);
        viewModel.ApplyUpdateInfo(new UpdateInfo(
            new Version(2, 8, 0),
            new Uri("https://github.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0")));

        viewModel.ApplyUpdateInfo(null);

        Assert.False(viewModel.IsUpdateAvailable);
        Assert.Empty(viewModel.UpdateAvailableText);
        Assert.Null(viewModel.UpdateDownloadUri);
    }

    [Fact]
    public void ApplyUpdateInfo_UsesUiDispatcher_WhenCalledOffUiThread()
    {
        var dispatcher = new DeferredTestUiDispatcher();
        var viewModel = CreateViewModel(uiDispatcher: dispatcher);
        var updateInfo = new UpdateInfo(
            new Version(2, 8, 0),
            new Uri("https://github.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0"));

        viewModel.ApplyUpdateInfo(updateInfo);

        Assert.False(viewModel.IsUpdateAvailable);
        Assert.NotNull(dispatcher.PostedAction);

        dispatcher.PostedAction();

        Assert.True(viewModel.IsUpdateAvailable);
        Assert.Equal(updateInfo.DownloadUri, viewModel.UpdateDownloadUri);
    }

    [Fact]
    public void LanguageChange_ReformatsAvailableUpdateText()
    {
        var localizationService = new LocalizationService();
        localizationService.SetLanguage(LocalizationService.LanguageEnglish);
        var viewModel = CreateViewModel(localizationService);
        viewModel.ApplyUpdateInfo(new UpdateInfo(
            new Version(2, 8, 0),
            new Uri("https://github.com/VoltKraft/immich-folder-watch/releases/tag/v2.8.0")));
        var changedProperties = new List<string?>();
        viewModel.PropertyChanged += (_, args) => changedProperties.Add(args.PropertyName);

        try
        {
            localizationService.SetLanguage(LocalizationService.LanguageGerman);

            Assert.Equal("Update v2.8.0 verfügbar", viewModel.UpdateAvailableText);
            Assert.Contains(nameof(MainWindowViewModel.UpdateAvailableText), changedProperties);
        }
        finally
        {
            localizationService.SetLanguage(LocalizationService.LanguageEnglish);
        }
    }

    [Fact]
    public void ProductVersionProvider_UsesInformationalVersionWithoutBuildMetadata()
    {
        var assembly = CreateDynamicAssembly(
            new Version(9, 8, 7, 6),
            informationalVersion: "2.8.0+build.42");

        var version = SharedProductVersionProvider.GetProductVersion(assembly);

        Assert.Equal(new Version(2, 8, 0), version);
    }

    [Fact]
    public void ProductVersionProvider_FallsBackToThreeComponentAssemblyVersion()
    {
        var assembly = CreateDynamicAssembly(
            new Version(9, 8, 7, 6),
            informationalVersion: "not-a-version");

        var version = SharedProductVersionProvider.GetProductVersion(assembly);

        Assert.Equal(new Version(9, 8, 7), version);
    }

    [Fact]
    public void Constructor_InitializesImmichChecksAsNeutral()
    {
        var viewModel = CreateViewModel();

        Assert.Equal(StatusTone.Neutral, viewModel.ImmichUrlStatusTone);
        Assert.Equal(StatusTone.Neutral, viewModel.ImmichApiKeyStatusTone);
        Assert.Equal(StatusTone.Neutral, viewModel.ImmichPermissionsStatusTone);
        Assert.NotEmpty(viewModel.ImmichPermissionStatuses);
        Assert.All(viewModel.ImmichPermissionStatuses, item => Assert.Equal(StatusTone.Neutral, item.StatusTone));
    }

    [Fact]
    public void SetImmichCheckInProgress_UsesInfoToneForChecksAndPermissions()
    {
        var viewModel = CreateViewModel();

        viewModel.SetImmichCheckInProgress();

        Assert.Equal(StatusTone.Info, viewModel.ImmichUrlStatusTone);
        Assert.Equal(StatusTone.Info, viewModel.ImmichApiKeyStatusTone);
        Assert.Equal(StatusTone.Info, viewModel.ImmichPermissionsStatusTone);
        Assert.NotEmpty(viewModel.ImmichPermissionStatuses);
        Assert.All(viewModel.ImmichPermissionStatuses, item => Assert.Equal(StatusTone.Info, item.StatusTone));
    }

    [Fact]
    public void ApplyImmichCheckResult_MapsCheckStatesToStatusTones()
    {
        var viewModel = CreateViewModel();

        viewModel.ApplyImmichCheckResult(new ImmichAccessCheckResult
        {
            UrlState = CheckState.Passed,
            ApiKeyState = CheckState.Failed,
            PermissionsState = CheckState.Warning,
            PermissionResults =
            [
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Asset Upload",
                    PermissionName = "asset.upload",
                    State = CheckState.Passed,
                    Message = "Upload assets is permitted.",
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Album Read",
                    PermissionName = "album.read",
                    State = CheckState.Warning,
                    Message = "Album access is limited.",
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Album Create",
                    PermissionName = "album.create",
                    State = CheckState.Failed,
                    Message = "Album creation is not permitted.",
                },
                new ImmichPermissionCheckResult
                {
                    DisplayName = "Add Asset To Album",
                    PermissionName = "albumAsset.create",
                    State = CheckState.Checking,
                    Message = "Checking...",
                },
            ],
        });

        Assert.Equal(StatusTone.Success, viewModel.ImmichUrlStatusTone);
        Assert.Equal(StatusTone.Error, viewModel.ImmichApiKeyStatusTone);
        Assert.Equal(StatusTone.Warning, viewModel.ImmichPermissionsStatusTone);
        Assert.Collection(
            viewModel.ImmichPermissionStatuses,
            item => Assert.Equal(StatusTone.Success, item.StatusTone),
            item => Assert.Equal(StatusTone.Warning, item.StatusTone),
            item => Assert.Equal(StatusTone.Error, item.StatusTone),
            item => Assert.Equal(StatusTone.Info, item.StatusTone));
    }

    [Fact]
    public void StatusToneMapper_MapsServerConnectionToExpectedTones()
    {
        Assert.Equal(StatusTone.Neutral, StatusToneMapper.FromServerConnection(ServerConnectionState.Unknown));
        Assert.Equal(StatusTone.Info, StatusToneMapper.FromServerConnection(ServerConnectionState.Checking));
        Assert.Equal(StatusTone.Success, StatusToneMapper.FromServerConnection(ServerConnectionState.Ok));
        Assert.Equal(StatusTone.Error, StatusToneMapper.FromServerConnection(ServerConnectionState.Error));
    }

    [Fact]
    public void ImmichApiKey_UsesMaskedDisplay_ForRealKeyByDefault()
    {
        var viewModel = CreateViewModel();

        viewModel.ImmichApiKey = "demo-key";

        Assert.True(viewModel.ShouldMaskImmichApiKey);
        Assert.False(viewModel.RevealImmichApiKey);
        Assert.False(viewModel.ShowPlainImmichApiKeyInput);
        Assert.True(viewModel.ShowImmichApiKeyRevealButton);
        Assert.False(viewModel.IsImmichApiKeyPlaceholder);
    }

    [Fact]
    public void ImmichApiKey_UsesPlainDisplay_ForPlaceholderValue()
    {
        var viewModel = CreateViewModel();

        viewModel.ImmichApiKey = AppConfigValidator.ExampleApiKeyPlaceholder;

        Assert.False(viewModel.ShouldMaskImmichApiKey);
        Assert.True(viewModel.RevealImmichApiKey);
        Assert.True(viewModel.ShowPlainImmichApiKeyInput);
        Assert.False(viewModel.ShowImmichApiKeyRevealButton);
        Assert.True(viewModel.IsImmichApiKeyPlaceholder);
    }

    [Fact]
    public void ToggleImmichApiKeyVisibility_TogglesMasking_ForRealKey()
    {
        var viewModel = CreateViewModel();
        viewModel.ImmichApiKey = "demo-key";

        viewModel.ToggleImmichApiKeyVisibility();

        Assert.False(viewModel.ShouldMaskImmichApiKey);
        Assert.True(viewModel.RevealImmichApiKey);
        Assert.True(viewModel.ShowPlainImmichApiKeyInput);

        viewModel.ToggleImmichApiKeyVisibility();

        Assert.True(viewModel.ShouldMaskImmichApiKey);
        Assert.False(viewModel.RevealImmichApiKey);
        Assert.False(viewModel.ShowPlainImmichApiKeyInput);
    }

    [Fact]
    public void ImmichApiKey_SwitchingFromPlaceholderToRealKey_ReenablesMasking()
    {
        var viewModel = CreateViewModel();
        viewModel.ImmichApiKey = AppConfigValidator.ExampleApiKeyPlaceholder;

        viewModel.ImmichApiKey = "demo-key";

        Assert.True(viewModel.ShouldMaskImmichApiKey);
        Assert.False(viewModel.RevealImmichApiKey);
        Assert.False(viewModel.ShowPlainImmichApiKeyInput);
        Assert.True(viewModel.ShowImmichApiKeyRevealButton);
    }

    [Fact]
    public void Load_ResetsImmichApiKeyVisibility_ForRealKey()
    {
        var viewModel = CreateViewModel();
        viewModel.ImmichApiKey = "demo-key";

        viewModel.ToggleImmichApiKeyVisibility();
        viewModel.Load(new AppConfig
        {
            Immich = new ImmichSettings
            {
                ServerApiUrl = "https://immich.example.com/api",
                ApiKey = "demo-key",
            },
        });

        Assert.True(viewModel.ShouldMaskImmichApiKey);
        Assert.False(viewModel.RevealImmichApiKey);
        Assert.False(viewModel.ShowPlainImmichApiKeyInput);
        Assert.True(viewModel.ShowImmichApiKeyRevealButton);
    }

    [Fact]
    public void ImmichApiKey_UsesPlainDisplay_WhenEmpty()
    {
        var viewModel = CreateViewModel();
        viewModel.ImmichApiKey = string.Empty;

        Assert.False(viewModel.ShouldMaskImmichApiKey);
        Assert.False(viewModel.RevealImmichApiKey);
        Assert.True(viewModel.ShowPlainImmichApiKeyInput);
        Assert.False(viewModel.ShowImmichApiKeyRevealButton);
    }

    [Fact]
    public void Constructor_CreatesCollapsedDefaultSourceWithOfficialImageExtensions()
    {
        var viewModel = CreateViewModel();

        Assert.Single(viewModel.Sources);
        Assert.Equal(JoinLines(ExpectedDefaultImageExtensions), viewModel.Sources[0].ExtensionsText);
        Assert.False(viewModel.Sources[0].ShowAdvancedOptions);
        Assert.False(viewModel.Sources[0].IncludeSubdirectories);
        Assert.False(viewModel.Sources[0].DeleteAfterUpload);
        Assert.False(viewModel.Sources[0].ShowExcludeDirectories);
        Assert.Equal(string.Empty, viewModel.Sources[0].ExcludeDirectoriesText);
        Assert.Equal(string.Empty, viewModel.Sources[0].ExcludeFileNamesText);
    }

    [Fact]
    public void CreateImmichCheckConfig_IncludesCurrentAlbumAssignments()
    {
        var viewModel = CreateViewModel();
        viewModel.Sources.Clear();
        viewModel.Sources.Add(new WatchSourceItem
        {
            Path = @"C:\Users\jan\Pictures\Screenshots",
            AlbumName = "Screenshots",
            IncludeSubdirectories = true,
            ExtensionsText = ".png\r\njpg",
            ExcludeDirectoriesText = "private\r\n**/cache",
            ExcludeFileNamesText = "Thumbs.db\r\n*.tmp",
        });

        var config = viewModel.CreateImmichCheckConfig();

        Assert.Single(config.Watch.Sources);
        Assert.Equal("Screenshots", config.Watch.Sources[0].AlbumName);
        Assert.True(config.Watch.Sources[0].IncludeSubdirectories);
        Assert.Equal([".png", "jpg"], config.Watch.Sources[0].Extensions);
        Assert.Equal(["private", "**/cache"], config.Watch.Sources[0].ExcludeDirectories);
        Assert.Equal(["Thumbs.db", "*.tmp"], config.Watch.Sources[0].ExcludeFileNames);
    }

    [Fact]
    public void AddSource_UsesTheSameDefaultValuesAsTheInitialSource()
    {
        var viewModel = CreateViewModel();
        viewModel.Sources.Clear();

        viewModel.AddSource();

        Assert.Single(viewModel.Sources);
        Assert.Equal(JoinLines(ExpectedDefaultImageExtensions), viewModel.Sources[0].ExtensionsText);
        Assert.False(viewModel.Sources[0].ShowAdvancedOptions);
        Assert.False(viewModel.Sources[0].ShowExcludeDirectories);
    }

    [Fact]
    public void Load_PopulatesPerSourceFilterFields()
    {
        var viewModel = CreateViewModel();

        viewModel.Load(new AppConfig
        {
            Watch = new WatchSettings
            {
                Sources =
                {
                    new WatchSourceSettings
                    {
                        Path = @"C:\Users\jan\Pictures\Screenshots",
                        AlbumName = "Screenshots",
                        IncludeSubdirectories = true,
                        DeleteAfterUpload = true,
                        Extensions = [".png", ".jpg"],
                        ExcludeDirectories = ["private", "**/cache"],
                        ExcludeFileNames = ["Thumbs.db", "*.tmp"],
                    },
                },
            },
        });

        Assert.Single(viewModel.Sources);
        Assert.Equal(JoinLines(".png", ".jpg"), viewModel.Sources[0].ExtensionsText);
        Assert.Equal(JoinLines("private", "**/cache"), viewModel.Sources[0].ExcludeDirectoriesText);
        Assert.Equal(JoinLines("Thumbs.db", "*.tmp"), viewModel.Sources[0].ExcludeFileNamesText);
        Assert.False(viewModel.Sources[0].ShowAdvancedOptions);
        Assert.True(viewModel.Sources[0].ShowExcludeDirectories);
        Assert.True(viewModel.Sources[0].DeleteAfterUpload);
    }

    [Fact]
    public void Load_WithNoSources_CreatesTheDefaultSource()
    {
        var viewModel = CreateViewModel();

        viewModel.Load(new AppConfig());

        Assert.Single(viewModel.Sources);
        Assert.Equal(JoinLines(ExpectedDefaultImageExtensions), viewModel.Sources[0].ExtensionsText);
        Assert.False(viewModel.Sources[0].ShowAdvancedOptions);
        Assert.False(viewModel.Sources[0].ShowExcludeDirectories);
    }

    [Fact]
    public void TryCreateConfig_PreservesHiddenExcludeDirectories()
    {
        var viewModel = CreateViewModel();
        viewModel.Sources.Clear();
        viewModel.Sources.Add(new WatchSourceItem
        {
            Path = @"C:\Users\jan\Pictures\Camera",
            AlbumName = "Camera",
            IncludeSubdirectories = false,
            DeleteAfterUpload = true,
            ExtensionsText = ".heic\r\n.jpeg",
            ExcludeDirectoriesText = "**/cache",
            ExcludeFileNamesText = "*.tmp",
        });

        var success = viewModel.TryCreateConfig(out var config, out var errors);

        Assert.True(success);
        Assert.Empty(errors);
        Assert.Single(config.Watch.Sources);
        Assert.Equal([".heic", ".jpeg"], config.Watch.Sources[0].Extensions);
        Assert.Equal(["**/cache"], config.Watch.Sources[0].ExcludeDirectories);
        Assert.Equal(["*.tmp"], config.Watch.Sources[0].ExcludeFileNames);
        Assert.True(config.Watch.Sources[0].DeleteAfterUpload);
    }

    [Fact]
    public void IncludeSubdirectories_TogglesShowExcludeDirectories_WithoutClearingValues()
    {
        var source = new WatchSourceItem
        {
            ExcludeDirectoriesText = JoinLines("private", "**/cache"),
        };

        Assert.False(source.ShowExcludeDirectories);

        source.IncludeSubdirectories = true;

        Assert.True(source.ShowExcludeDirectories);

        source.IncludeSubdirectories = false;

        Assert.False(source.ShowExcludeDirectories);
        Assert.Equal(JoinLines("private", "**/cache"), source.ExcludeDirectoriesText);
    }

    private static string JoinLines(params string[] values)
    {
        return string.Join(Environment.NewLine, values);
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
}
