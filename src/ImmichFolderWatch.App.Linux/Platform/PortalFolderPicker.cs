using Avalonia.Controls;
using Avalonia.Platform.Storage;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class PortalFolderPicker
{
    private readonly Func<TopLevel?> _topLevelAccessor;
    private readonly ILogger<PortalFolderPicker> _logger;

    public PortalFolderPicker(Func<TopLevel?> topLevelAccessor)
        : this(topLevelAccessor, NullLogger<PortalFolderPicker>.Instance)
    {
    }

    public PortalFolderPicker(Func<TopLevel?> topLevelAccessor, ILogger<PortalFolderPicker> logger)
    {
        _topLevelAccessor = topLevelAccessor;
        _logger = logger;
    }

    public async Task<string?> PickFolderAsync(string title, CancellationToken cancellationToken = default)
    {
        var topLevel = _topLevelAccessor();
        if (topLevel is null)
        {
            _logger.LogWarning("Folder picker invoked before a top-level window is available.");
            return null;
        }

        var storage = topLevel.StorageProvider;
        if (storage is null || !storage.CanPickFolder)
        {
            _logger.LogWarning("Folder picker not supported by the current platform StorageProvider.");
            return null;
        }

        try
        {
            _logger.LogInformation("Opening folder picker via FileChooser portal…");
            var folders = await storage.OpenFolderPickerAsync(new FolderPickerOpenOptions
            {
                Title = title,
                AllowMultiple = false,
            });

            var first = folders.Count > 0 ? folders[0] : null;
            if (first is null)
            {
                _logger.LogInformation("Folder picker dismissed without a selection.");
                return null;
            }

            // TryGetLocalPath requires Documents portal access for doc-handle
            // URIs (/run/user/$UID/doc/<id>/...). Ran on the UI thread on
            // purpose — the StorageItem is bound to Avalonia's main loop.
            var path = first.TryGetLocalPath();
            if (string.IsNullOrEmpty(path))
            {
                _logger.LogWarning("Picked folder has no local path; URI was {Uri}", first.Path);
            }
            else
            {
                _logger.LogInformation("Folder picker returned {Path}", path);
            }
            return path;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Folder picker failed");
            return null;
        }
    }
}
