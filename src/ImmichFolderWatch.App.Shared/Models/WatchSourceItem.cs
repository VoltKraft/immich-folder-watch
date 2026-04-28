using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.App.Shared.Models;

public sealed class WatchSourceItem : BindableBase
{
    private string _path = string.Empty;
    private string _albumName = string.Empty;
    private string _extensionsText = string.Empty;
    private string _excludeDirectoriesText = string.Empty;
    private string _excludeFileNamesText = string.Empty;
    private bool _includeSubdirectories;
    private bool _showAdvancedOptions;
    private bool _albumNameTouchedByUser;
    private bool _hasAutoFilledAlbumName;
    private bool _isApplyingAlbumSuggestion;
    private string _syncMode = WatchSourceSyncModes.UploadNew;

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
        set
        {
            if (SetProperty(ref _includeSubdirectories, value))
            {
                RaisePropertyChanged(nameof(ShowExcludeDirectories));
            }
        }
    }

    public string ExtensionsText
    {
        get => _extensionsText;
        set => SetProperty(ref _extensionsText, value);
    }

    public string ExcludeDirectoriesText
    {
        get => _excludeDirectoriesText;
        set => SetProperty(ref _excludeDirectoriesText, value);
    }

    public string ExcludeFileNamesText
    {
        get => _excludeFileNamesText;
        set => SetProperty(ref _excludeFileNamesText, value);
    }

    public bool ShowAdvancedOptions
    {
        get => _showAdvancedOptions;
        set => SetProperty(ref _showAdvancedOptions, value);
    }

    public string SyncMode
    {
        get => _syncMode;
        set
        {
            if (SetProperty(ref _syncMode, WatchSourceSyncModes.Normalize(value)))
            {
                RaisePropertyChanged(nameof(ShowIncludeSubdirectories));
                RaisePropertyChanged(nameof(ShowExcludeDirectories));
            }
        }
    }

    public bool ShowIncludeSubdirectories =>
        !string.Equals(_syncMode, WatchSourceSyncModes.Sync, StringComparison.Ordinal);

    public bool ShowExcludeDirectories =>
        ShowIncludeSubdirectories && IncludeSubdirectories;

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
            var trimmedPath = path.Trim().TrimEnd('\\', '/');
            if (string.IsNullOrWhiteSpace(trimmedPath))
            {
                return false;
            }

            var lastSeparatorIndex = trimmedPath.LastIndexOfAny(['\\', '/']);
            albumName = lastSeparatorIndex >= 0
                ? trimmedPath[(lastSeparatorIndex + 1)..]
                : trimmedPath;

            return !string.IsNullOrWhiteSpace(albumName);
        }
        catch (Exception)
        {
            albumName = string.Empty;
            return false;
        }
    }
}
