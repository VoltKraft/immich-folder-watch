using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IUploadBatchQueue
{
    int Count { get; }

    bool TryEnqueue(UploadAssetRequest request);

    IReadOnlyList<UploadAssetRequest> DequeueBatch(int maxBatchSize);
}
