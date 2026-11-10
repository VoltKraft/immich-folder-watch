using Microsoft.Win32.SafeHandles;

namespace ImmichFolderWatch.Core.Services;

/// <summary>A media stream and metadata tied to the same opened regular file, plus pinned parents.</summary>
public sealed class SecureWatchFile : IDisposable
{
    private readonly SecureDirectoryChain _parent;
    private readonly string _name;
    private readonly bool _writableMetadata;
    private bool _disposed;

    internal SecureWatchFile(SecureDirectoryChain parent, string name, SafeFileHandle handle, bool writableMetadata)
    {
        _parent = parent;
        _name = name;
        _writableMetadata = writableMetadata;
        try { Stream = new FileStream(handle, FileAccess.Read); }
        catch { handle.Dispose(); throw; }
    }

    public FileStream Stream { get; }
    public long Length => SecureNativeFileSystem.GetMetadata(Stream.SafeFileHandle).Length;
    public DateTime CreationTimeUtc => SecureNativeFileSystem.GetMetadata(Stream.SafeFileHandle).CreationTimeUtc;
    public DateTime LastWriteTimeUtc => SecureNativeFileSystem.GetMetadata(Stream.SafeFileHandle).LastWriteTimeUtc;

    public void SetTimestamps(DateTime createdUtc, DateTime modifiedUtc)
    {
        if (!_writableMetadata) throw new InvalidOperationException("This lease does not permit changing file metadata.");
        SecureNativeFileSystem.SetTimestamps(Stream.SafeFileHandle, createdUtc, modifiedUtc);
    }

    public bool IsCurrentEntry()
    {
        try
        {
            var current = SecureNativeFileSystem.GetEntryMetadata(_parent.Handle, _name);
            return current.IsRegularFile && !current.IsLink
                && SecureNativeFileSystem.GetMetadata(Stream.SafeFileHandle).SameIdentity(current);
        }
        catch (FileNotFoundException) { return false; }
        catch (DirectoryNotFoundException) { return false; }
    }

    /// <summary>Deletes only this file's identity; a changed directory entry is never deleted as a substitute.</summary>
    public void Delete() => SecureNativeFileSystem.DeleteAuthorizedFile(_parent.Handle, _name, Stream.SafeFileHandle, _parent.Transactions);

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        Stream.Dispose();
        _parent.Dispose();
    }
}

/// <summary>A download staged in a private pinned transaction directory and published without replacement.</summary>
public sealed class SecureDownloadLease : IDisposable
{
    private readonly SecureDirectoryChain _parent;
    private readonly string _destination;
    private readonly SecureTransactionDirectory _transaction;
    private bool _completed;
    private bool _disposed;

    internal SecureDownloadLease(SecureDirectoryChain parent, string destination)
    {
        _parent = parent;
        _destination = destination;
        _transaction = SecureNativeFileSystem.CreateTransaction(parent.Handle, parent.Transactions);
        try
        {
            var file = SecureNativeFileSystem.OpenFile(_transaction.Handle, "payload", writableMetadata: true, create: true);
            try { Stream = new FileStream(file, FileAccess.ReadWrite); }
            catch
            {
                try { SecureNativeFileSystem.DeletePrivateFile(_transaction.Handle, "payload", file); }
                finally { file.Dispose(); }
                throw;
            }
        }
        catch
        {
            _transaction.Dispose();
            throw;
        }
    }

    public FileStream Stream { get; }
    public long Length => Stream.Length;
    public DateTime CreationTimeUtc => SecureNativeFileSystem.GetMetadata(Stream.SafeFileHandle).CreationTimeUtc;
    public DateTime LastWriteTimeUtc => SecureNativeFileSystem.GetMetadata(Stream.SafeFileHandle).LastWriteTimeUtc;
    public long GetAvailableFreeSpace() => SecureNativeFileSystem.GetAvailableFreeSpace(Stream.SafeFileHandle);

    public void SetTimestamps(DateTime createdUtc, DateTime modifiedUtc)
    {
        Stream.Flush();
        SecureNativeFileSystem.SetTimestamps(Stream.SafeFileHandle, createdUtc, modifiedUtc);
    }

    public void CompleteNoReplace()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (_completed) throw new InvalidOperationException("The download has already been published.");
        Stream.Flush(flushToDisk: true);
        SecureNativeFileSystem.PublishFile(_transaction.Handle, "payload", Stream.SafeFileHandle, _parent.Handle, _destination);
        _completed = true;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        try
        {
            if (!_completed)
                SecureNativeFileSystem.DeletePrivateFile(_transaction.Handle, "payload", Stream.SafeFileHandle);
        }
        finally
        {
            Stream.Dispose();
            try { _transaction.Dispose(); }
            finally { _parent.Dispose(); }
        }
    }
}
