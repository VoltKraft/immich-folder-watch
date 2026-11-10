using ImmichFolderWatch.Core.Interfaces;

namespace ImmichFolderWatch.Core.Services;

public sealed class LocalFileDeletionService : ILocalFileDeletionService
{
    public void Delete(string filePath)
    {
        var fullPath = Path.GetFullPath(filePath);
        using var root = SecureWatchRoot.Open(Path.GetDirectoryName(fullPath)!);
        root.DeleteFile(Path.GetFileName(fullPath));
    }
}
