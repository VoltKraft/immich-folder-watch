using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Core.Interfaces;

public interface ILocalFileDeletionService
{
    void Delete(string filePath);

    /// <summary>Deletes the exact authorized file identity; never reopens a display pathname.</summary>
    void Delete(SecureWatchFile file) => file.Delete();
}
