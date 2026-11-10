using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Core.Models;

public sealed record UploadAssetRequest(
    string FilePath,
    string AlbumName,
    string SourcePath = "",
    int Attempt = 1)
{
    /// <summary>The source capability pinned for the worker session; never inferred from a later pathname lookup.</summary>
    public SecureWatchRoot? SourceRoot { get; init; }

    /// <summary>Borrowed file lease for one transfer attempt. Its caller owns disposal.</summary>
    public SecureWatchFile? OpenedFile { get; init; }
}
