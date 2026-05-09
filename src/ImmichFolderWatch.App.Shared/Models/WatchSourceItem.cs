using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.App.Shared.Models;

public sealed class WatchSourceItem : BindableBase
{
    private string _path = string.Empty;
    private string _displayPath = string.Empty;
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
                if (!string.IsNullOrEmpty(_displayPath))
                {
                    RaisePropertyChanged(nameof(DisplayPath));
                }
            }
        }
    }

    /// <summary>
    /// Transient, non-persisted "user-friendly" view on <see cref="Path"/>.
    /// On Linux, when the FileChooser portal hands us a doc-portal FUSE
    /// mount path (<c>/run/user/$UID/doc/&lt;token&gt;/...</c>), the UI
    /// binds to this so the user sees their original path
    /// (<c>~/Immich/Photos</c>) while <see cref="Path"/> keeps the mount
    /// the FolderWatchWorker actually reads from. Defaults to
    /// <see cref="Path"/> when no override is set, so the WPF head and
    /// any platform without doc-portal handling sees identical
    /// behaviour. User edits flow back into <see cref="Path"/> verbatim
    /// (treated as a manual host-path override). Use
    /// <see cref="SetPortalPath"/> from the portal-pick flow to set the
    /// two values independently.
    /// </summary>
    public string DisplayPath
    {
        get => string.IsNullOrEmpty(_displayPath) ? _path : _displayPath;
        set
        {
            if (SetProperty(ref _displayPath, value))
            {
                if (!string.Equals(_path, value, StringComparison.Ordinal))
                {
                    Path = value;
                }
            }
        }
    }

    /// <summary>
    /// Sets <see cref="Path"/> to the FUSE mount path the FolderWatch
    /// Worker has to read AND <see cref="DisplayPath"/> to the host
    /// path the user picked, without the user-edit mirror that would
    /// otherwise clobber the mount path back to the host path.
    /// </summary>
    public void SetPortalPath(string mountPath, string hostPath)
    {
        Path = mountPath ?? string.Empty;

        var resolved = string.IsNullOrEmpty(hostPath) ? string.Empty : hostPath;
        if (!string.Equals(_displayPath, resolved, StringComparison.Ordinal))
        {
            _displayPath = resolved;
            RaisePropertyChanged(nameof(DisplayPath));
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
