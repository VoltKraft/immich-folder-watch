namespace ImmichFolderWatch.Core.Interfaces;

/// <summary>Durable authority to mutate albums created by this source and account.
/// Imported albums and legacy name-only mappings never confer ownership.</summary>
public interface IAlbumOwnershipStore
{
    /// <summary>Revokes authority after unobserved filesystem changes while the host was stopped.</summary>
    Task RevokeAlbumOwnershipAsync(string accountScope, CancellationToken cancellationToken);
    Task<string?> GetOwnedAlbumAsync(string accountScope, string sourcePath, string directoryName, CancellationToken cancellationToken);
    Task SaveOwnedAlbumAsync(string accountScope, string sourcePath, string directoryName, string albumId, CancellationToken cancellationToken);
    Task RemoveOwnedAlbumAsync(string accountScope, string sourcePath, string directoryName, string albumId, CancellationToken cancellationToken);
    Task MoveOwnedAlbumAsync(string accountScope, string sourcePath, string oldName, string newName, string albumId, CancellationToken cancellationToken);
}
