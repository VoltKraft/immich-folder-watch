using ImmichFolderWatch.Core.Interfaces;

namespace ImmichFolderWatch.Core.Services;

public sealed class LocalFileDeletionService : ILocalFileDeletionService
{
    public void Delete(string filePath)
    {
        File.Delete(filePath);
    }
}
