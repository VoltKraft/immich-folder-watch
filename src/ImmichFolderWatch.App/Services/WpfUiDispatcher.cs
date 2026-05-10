using System.Windows;
using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.App.Services;

public sealed class WpfUiDispatcher : IUiDispatcher
{
    public bool IsOnUiThread =>
        Application.Current?.Dispatcher.CheckAccess() ?? true;

    public void Post(Action action)
    {
        ArgumentNullException.ThrowIfNull(action);
        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher is null)
        {
            action();
            return;
        }
        dispatcher.BeginInvoke(action);
    }
}
