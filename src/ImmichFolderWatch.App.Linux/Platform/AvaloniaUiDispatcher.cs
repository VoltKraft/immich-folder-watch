using Avalonia.Threading;
using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class AvaloniaUiDispatcher : IUiDispatcher
{
    public bool IsOnUiThread => Dispatcher.UIThread.CheckAccess();

    public void Post(Action action)
    {
        ArgumentNullException.ThrowIfNull(action);
        Dispatcher.UIThread.Post(action);
    }
}
