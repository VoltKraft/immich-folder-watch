using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Core.Interfaces;

public interface IUploadBatchQueue
{
    int Count { get; }

    bool TryEnqueue(UploadAssetRequest request);

    /// <summary>
    /// Removes up to <paramref name="maxBatchSize"/> pending files in modification-time order.
    /// Files with unavailable timestamps follow dated files; equal timestamps retain enqueue order.
    /// </summary>
    IReadOnlyList<UploadAssetRequest> DequeueBatch(int maxBatchSize, string transferOrder = TransferOrders.NewestFirst);
}
