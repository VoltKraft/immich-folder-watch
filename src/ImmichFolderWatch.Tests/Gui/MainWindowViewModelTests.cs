using ImmichFolderWatch.Core.Models;
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
}
