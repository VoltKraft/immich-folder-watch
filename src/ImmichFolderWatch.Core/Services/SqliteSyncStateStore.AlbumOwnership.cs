namespace ImmichFolderWatch.Core.Services;

public sealed partial class SqliteSyncStateStore
{
    public async Task RevokeAlbumOwnershipAsync(string accountScope, CancellationToken cancellationToken)
    {
        ValidateAccountScope(accountScope);
        await InitializeAsync(cancellationToken);
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = "DELETE FROM owned_albums WHERE account_scope=$account;";
        command.Parameters.AddWithValue("$account", accountScope);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task<string?> GetOwnedAlbumAsync(string accountScope, string sourcePath, string directoryName, CancellationToken cancellationToken)
    {
        await InitializeAsync(cancellationToken);
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = "SELECT album_id FROM owned_albums WHERE account_scope=$account AND source_key=$source AND directory_key=$directory;";
        command.Parameters.AddWithValue("$account", accountScope);
        command.Parameters.AddWithValue("$source", GetPathKey(NormalizeSourcePath(sourcePath)));
        command.Parameters.AddWithValue("$directory", GetAlbumDirectoryKey(directoryName));
        return await command.ExecuteScalarAsync(cancellationToken) as string;
    }

    public async Task SaveOwnedAlbumAsync(string accountScope, string sourcePath, string directoryName, string albumId, CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(albumId);
        ValidateAccountScope(accountScope);
        await InitializeAsync(cancellationToken);
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        // Never replace existing authority implicitly, even under concurrent callbacks.
        command.CommandText = "INSERT INTO owned_albums (account_scope,source_key,directory_key,album_id) VALUES ($account,$source,$directory,$id);";
        command.Parameters.AddWithValue("$account", accountScope);
        command.Parameters.AddWithValue("$source", GetPathKey(NormalizeSourcePath(sourcePath)));
        command.Parameters.AddWithValue("$directory", GetAlbumDirectoryKey(directoryName));
        command.Parameters.AddWithValue("$id", albumId);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task RemoveOwnedAlbumAsync(string accountScope, string sourcePath, string directoryName, string albumId, CancellationToken cancellationToken)
    {
        await InitializeAsync(cancellationToken);
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = "DELETE FROM owned_albums WHERE account_scope=$account AND source_key=$source AND directory_key=$directory AND album_id=$id;";
        command.Parameters.AddWithValue("$account", accountScope);
        command.Parameters.AddWithValue("$source", GetPathKey(NormalizeSourcePath(sourcePath)));
        command.Parameters.AddWithValue("$directory", GetAlbumDirectoryKey(directoryName));
        command.Parameters.AddWithValue("$id", albumId);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task MoveOwnedAlbumAsync(string accountScope, string sourcePath, string oldName, string newName, string albumId, CancellationToken cancellationToken)
    {
        await InitializeAsync(cancellationToken);
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = connection.CreateCommand();
        command.CommandText = "UPDATE owned_albums SET directory_key=$new WHERE account_scope=$account AND source_key=$source AND directory_key=$old AND album_id=$id;";
        command.Parameters.AddWithValue("$account", accountScope);
        command.Parameters.AddWithValue("$source", GetPathKey(NormalizeSourcePath(sourcePath)));
        command.Parameters.AddWithValue("$old", GetAlbumDirectoryKey(oldName));
        command.Parameters.AddWithValue("$new", GetAlbumDirectoryKey(newName));
        command.Parameters.AddWithValue("$id", albumId);
        if (await command.ExecuteNonQueryAsync(cancellationToken) != 1)
        {
            throw new InvalidOperationException("Album ownership changed during rename.");
        }
    }

    private string GetAlbumDirectoryKey(string name)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        if (name is "." or ".." || name.IndexOfAny(new[] { '/', '\\' }) >= 0 || Path.IsPathRooted(name))
        {
            throw new ArgumentException("Album binding requires a first-level directory name.", nameof(name));
        }

        return GetPathKey(name);
    }
}
