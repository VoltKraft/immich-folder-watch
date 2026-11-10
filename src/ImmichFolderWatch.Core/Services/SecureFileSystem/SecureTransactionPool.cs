using Microsoft.Win32.SafeHandles;

namespace ImmichFolderWatch.Core.Services;

/// <summary>
/// Retains at most 64 protected Linux transaction containers, keyed by parent identity.
/// The outer name is deliberately never removed: Linux cannot atomically unlink a directory
/// name conditional on inode identity. Inner entries are removable through the private handle.
/// </summary>
internal sealed class SecureTransactionPool(SecureWatchTestHooks? hooks = null)
{
    internal const int Capacity = 64;
    private readonly Dictionary<(ulong Volume, ulong File, ulong FileHigh), (string Name, SafeFileHandle Handle, SafeFileHandle Parent, long LastUse)> _containers = new();
    private long _sequence;
    private readonly object _gate = new();
    private int _references = 1;
    public SecureWatchTestHooks? Hooks { get; } = hooks;

    public void AddReference()
    {
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_references == 0, this);
            _references++;
        }
    }

    public (string Name, SafeFileHandle Handle) GetContainer(SafeFileHandle parent)
    {
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_references == 0, this);
            var metadata = SecureNativeFileSystem.GetMetadata(parent);
            var key = (metadata.Volume, metadata.FileId, metadata.FileIdHigh);
            if (!_containers.TryGetValue(key, out var container))
            {
                var pinnedParent = SecureNativeFileSystem.Duplicate(parent);
                try
                {
                    var created = SecureNativeFileSystem.CreateProtectedContainer(pinnedParent);
                    container = (created.Name, created.Handle, pinnedParent, ++_sequence);
                    if (_containers.Count == Capacity)
                    {
                        var oldest = _containers.MinBy(entry => entry.Value.LastUse);
                        _containers.Remove(oldest.Key);
                        // Operations own duplicate handles. Never reopen an evicted pathname;
                        // the next visit creates another protected random container.
                        oldest.Value.Handle.Dispose();
                        oldest.Value.Parent.Dispose();
                    }
                    _containers.Add(key, container);
                    Hooks?.TransactionContainerCountChanged?.Invoke(_containers.Count);
                }
                catch { pinnedParent.Dispose(); throw; }
                Hooks?.TransactionContainerCreated?.Invoke(container.Name);
            }
            else
            {
                container.LastUse = ++_sequence;
                _containers[key] = container;
            }
            return (container.Name, SecureNativeFileSystem.Duplicate(container.Handle));
        }
    }

    public void Release()
    {
        lock (_gate)
        {
            if (--_references != 0) return;
            foreach (var container in _containers.Values)
            {
                container.Handle.Dispose();
                container.Parent.Dispose();
            }
            _containers.Clear();
        }
    }
}

internal sealed class SecureTransactionDirectory(SafeFileHandle parent, string name, SafeFileHandle handle, string displayPath) : IDisposable
{
    private bool _preserve;
    private bool _disposed;
    public SafeFileHandle Handle { get; } = handle;
    public string DisplayPath { get; } = displayPath;
    public void Preserve() => _preserve = true;
    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        try { if (!_preserve) SecureNativeFileSystem.RemovePrivateDirectory(parent, name, Handle); }
        finally { Handle.Dispose(); parent.Dispose(); }
    }
}

// Per-root deterministic race injection; never enabled by a production caller.
internal sealed class SecureWatchTestHooks
{
    public Action? DirectoryAuthorizedBeforeMove { get; init; }
    public Action<string>? TransactionContainerCreated { get; init; }
    public Action<int>? TransactionContainerCountChanged { get; init; }
}
