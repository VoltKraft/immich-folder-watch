using ImmichFolderWatch.App.Models;
using ImmichFolderWatch.App.Services;
using ImmichFolderWatch.App.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Gui;

public sealed class MainWindowViewModelTests
{
    private static readonly string[] ExpectedDefaultImageExtensions =
    {
        ".avif",
        ".bmp",
        ".gif",
        ".heic",
        ".heif",
        ".jp2",
        ".jpe",
        ".jpeg",
        ".jpg",
        ".insp",
        ".jxl",
        ".png",
        ".psd",
        ".raw",
        ".rw2",
        ".svg",
        ".tif",
        ".tiff",
        ".webp",
    };

    private static MainWindowViewModel CreateViewModel()
    {
        return new MainWindowViewModel(new SyncStatusProvider(), new AutostartManager(), LocalizationService.Instance);
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
}
