namespace ImmichFolderWatch.Core.Platform;

public interface IUiDispatcher
{
    bool IsOnUiThread { get; }

    void Post(Action action);
}
