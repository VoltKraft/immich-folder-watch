namespace ImmichFolderWatch.Core.Models;

public sealed record UploadAssetRequest(
    string FilePath,
    string AlbumName,
    string SourcePath = "");
