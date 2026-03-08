using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Gui.ViewModels;

namespace ImmichFolderWatch.Tests.Gui;

public sealed class MainWindowViewModelTests
{
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
}
