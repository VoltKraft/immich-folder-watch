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

        try
        {
            var folders = await topLevel.StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
            {
                Title = title,
                AllowMultiple = false,
            }).ConfigureAwait(false);

            var first = folders.FirstOrDefault();
            return first?.TryGetLocalPath();
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Folder picker failed");
            return null;
        }
    }
}
