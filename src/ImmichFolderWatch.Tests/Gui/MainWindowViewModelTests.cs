using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Gui.Models;
using ImmichFolderWatch.Gui.ViewModels;

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

    [Fact]
    public void ApplyServiceActionVisibility_UsesRestartLabel_WhenServiceIsRunning()
    {
        var viewModel = new MainWindowViewModel();

        viewModel.ApplyServiceActionVisibility(new ServiceStatusSnapshot
        {
            Exists = true,
            State = ServiceRunState.Running,
        });

        Assert.Equal("Save and Restart", viewModel.SaveActionButtonText);
    }

    [Fact]
    public void ApplyServiceActionVisibility_UsesStartLabel_WhenServiceIsStopped()
    {
        var viewModel = new MainWindowViewModel();

        viewModel.ApplyServiceActionVisibility(new ServiceStatusSnapshot
        {
            Exists = true,
            State = ServiceRunState.Stopped,
        });

        Assert.Equal("Save and Start", viewModel.SaveActionButtonText);
    }

    [Fact]
    public void ImmichApiKey_UsesMaskedDisplay_ForRealKeyByDefault()
    {
        var viewModel = new MainWindowViewModel();

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
        var viewModel = new MainWindowViewModel();

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
        var viewModel = new MainWindowViewModel
        {
            ImmichApiKey = "demo-key",
        };

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
        var viewModel = new MainWindowViewModel
        {
            ImmichApiKey = AppConfigValidator.ExampleApiKeyPlaceholder,
        };

        viewModel.ImmichApiKey = "demo-key";

        Assert.True(viewModel.ShouldMaskImmichApiKey);
        Assert.False(viewModel.RevealImmichApiKey);
        Assert.False(viewModel.ShowPlainImmichApiKeyInput);
        Assert.True(viewModel.ShowImmichApiKeyRevealButton);
    }

    [Fact]
    public void Load_ResetsImmichApiKeyVisibility_ForRealKey()
    {
        var viewModel = new MainWindowViewModel
        {
            ImmichApiKey = "demo-key",
        };

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
        var viewModel = new MainWindowViewModel
        {
            ImmichApiKey = string.Empty,
        };

        Assert.False(viewModel.ShouldMaskImmichApiKey);
        Assert.False(viewModel.RevealImmichApiKey);
        Assert.True(viewModel.ShowPlainImmichApiKeyInput);
        Assert.False(viewModel.ShowImmichApiKeyRevealButton);
    }

    [Fact]
    public void Constructor_CreatesCollapsedDefaultSourceWithOfficialImageExtensions()
    {
        var viewModel = new MainWindowViewModel();

        Assert.Single(viewModel.Sources);
        Assert.Equal(string.Join("\r\n", ExpectedDefaultImageExtensions), viewModel.Sources[0].ExtensionsText);
        Assert.False(viewModel.Sources[0].ShowAdvancedOptions);
        Assert.False(viewModel.Sources[0].IncludeSubdirectories);
        Assert.False(viewModel.Sources[0].ShowExcludeDirectories);
        Assert.Equal(string.Empty, viewModel.Sources[0].ExcludeDirectoriesText);
        Assert.Equal(string.Empty, viewModel.Sources[0].ExcludeFileNamesText);
    }

    [Fact]
    public void CreateImmichCheckConfig_IncludesCurrentAlbumAssignments()
    {
        var viewModel = new MainWindowViewModel();
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
        var viewModel = new MainWindowViewModel();
        viewModel.Sources.Clear();

        viewModel.AddSource();

        Assert.Single(viewModel.Sources);
        Assert.Equal(string.Join("\r\n", ExpectedDefaultImageExtensions), viewModel.Sources[0].ExtensionsText);
        Assert.False(viewModel.Sources[0].ShowAdvancedOptions);
        Assert.False(viewModel.Sources[0].ShowExcludeDirectories);
    }

    [Fact]
    public void Load_PopulatesPerSourceFilterFields()
    {
        var viewModel = new MainWindowViewModel();

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
        Assert.Equal(".png\r\n.jpg", viewModel.Sources[0].ExtensionsText);
        Assert.Equal("private\r\n**/cache", viewModel.Sources[0].ExcludeDirectoriesText);
        Assert.Equal("Thumbs.db\r\n*.tmp", viewModel.Sources[0].ExcludeFileNamesText);
        Assert.False(viewModel.Sources[0].ShowAdvancedOptions);
        Assert.True(viewModel.Sources[0].ShowExcludeDirectories);
    }

    [Fact]
    public void Load_WithNoSources_CreatesTheDefaultSource()
    {
        var viewModel = new MainWindowViewModel();

        viewModel.Load(new AppConfig());

        Assert.Single(viewModel.Sources);
        Assert.Equal(string.Join("\r\n", ExpectedDefaultImageExtensions), viewModel.Sources[0].ExtensionsText);
        Assert.False(viewModel.Sources[0].ShowAdvancedOptions);
        Assert.False(viewModel.Sources[0].ShowExcludeDirectories);
    }

    [Fact]
    public void TryCreateConfig_PreservesHiddenExcludeDirectories()
    {
        var viewModel = new MainWindowViewModel();
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
            ExcludeDirectoriesText = "private\r\n**/cache",
        };

        Assert.False(source.ShowExcludeDirectories);

        source.IncludeSubdirectories = true;

        Assert.True(source.ShowExcludeDirectories);

        source.IncludeSubdirectories = false;

        Assert.False(source.ShowExcludeDirectories);
        Assert.Equal("private\r\n**/cache", source.ExcludeDirectoriesText);
    }
}
