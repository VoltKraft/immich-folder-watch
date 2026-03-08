using ImmichFolderWatch.Gui.ViewModels;

namespace ImmichFolderWatch.Gui.Models;

public sealed class WatchSourceItem : BindableBase
{
    private string _path = string.Empty;
    private string _albumName = string.Empty;
    private bool _includeSubdirectories;

    public string Path
    {
        get => _path;
        set => SetProperty(ref _path, value);
    }

    public string AlbumName
    {
        get => _albumName;
        set => SetProperty(ref _albumName, value);
    }

    public bool IncludeSubdirectories
    {
        get => _includeSubdirectories;
        set => SetProperty(ref _includeSubdirectories, value);
    }
}
