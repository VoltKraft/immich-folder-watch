using ImmichFolderWatch.Gui.ViewModels;

namespace ImmichFolderWatch.Gui.Models;

public sealed class WatchSourceItem : BindableBase
{
    private string _path = string.Empty;
    private string _albumName = string.Empty;
    private bool _includeSubdirectories;
    private bool _albumNameTouchedByUser;
    private bool _hasAutoFilledAlbumName;
    private bool _isApplyingAlbumSuggestion;

    public string Path
    {
        get => _path;
        set
        {
            if (SetProperty(ref _path, value))
            {
                TrySuggestAlbumNameFromPath();
            }
        }
    }

    public string AlbumName
    {
        get => _albumName;
        set
        {
            if (SetProperty(ref _albumName, value) && !_isApplyingAlbumSuggestion)
            {
                _albumNameTouchedByUser = true;
            }
        }
    }

    public bool IncludeSubdirectories
    {
        get => _includeSubdirectories;
        set => SetProperty(ref _includeSubdirectories, value);
    }

    private void TrySuggestAlbumNameFromPath()
    {
        if (_hasAutoFilledAlbumName || _albumNameTouchedByUser || !string.IsNullOrWhiteSpace(_albumName))
        {
            return;
        }

        if (!TryGetSuggestedAlbumName(_path, out var suggestedAlbumName))
        {
            return;
        }

        _isApplyingAlbumSuggestion = true;
        try
        {
            AlbumName = suggestedAlbumName;
            _hasAutoFilledAlbumName = true;
        }
        finally
        {
            _isApplyingAlbumSuggestion = false;
        }
    }

    private static bool TryGetSuggestedAlbumName(string path, out string albumName)
    {
        albumName = string.Empty;

        if (string.IsNullOrWhiteSpace(path))
        {
            return false;
        }

        try
        {
            var trimmedPath = path.Trim().TrimEnd(System.IO.Path.DirectorySeparatorChar, System.IO.Path.AltDirectorySeparatorChar);
            if (string.IsNullOrWhiteSpace(trimmedPath))
            {
                return false;
            }

            albumName = System.IO.Path.GetFileName(trimmedPath);
            return !string.IsNullOrWhiteSpace(albumName);
        }
        catch (Exception)
        {
            albumName = string.Empty;
            return false;
        }
    }
}
