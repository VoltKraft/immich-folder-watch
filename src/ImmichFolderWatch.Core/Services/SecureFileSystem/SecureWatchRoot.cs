using Microsoft.Win32.SafeHandles;

namespace ImmichFolderWatch.Core.Services;

/// <summary>
/// Authorizes a source directory by its opened identity. Every operation resolves relative
/// components without following links. Renaming an authorized directory never redirects
/// operations into its replacement. Dispose only after source operations have stopped.
/// </summary>
public sealed class SecureWatchRoot : IDisposable
{
    internal const string InternalPrefix = ".ifw-internal-";
    private readonly SafeFileHandle _handle;
    private readonly SecureTransactionPool _transactions;
    private bool _disposed;

    private SecureWatchRoot(string rootPath, SafeFileHandle handle, SecureWatchTestHooks? hooks)
    {
        RootPath = rootPath;
        _handle = handle;
        _transactions = new SecureTransactionPool(hooks);
    }

    public string RootPath { get; }

    public static SecureWatchRoot Open(string rootPath) => Open(rootPath, hooks: null);

    internal static SecureWatchRoot Open(string rootPath, SecureWatchTestHooks? hooks)
    {
        var fullPath = Path.TrimEndingDirectorySeparator(Path.GetFullPath(rootPath));
        return new SecureWatchRoot(fullPath, SecureNativeFileSystem.OpenRoot(fullPath), hooks);
    }

    /// <summary>Internal transaction directories are never media or album sources.</summary>
    public static bool IsInternalPath(string relativePath) => relativePath
        .Split(new[] { '/', '\\' }, StringSplitOptions.RemoveEmptyEntries)
        .Any(component => component.StartsWith(InternalPrefix, StringComparison.OrdinalIgnoreCase));

    public SecureWatchFile OpenRead(string relativePath, bool writableMetadata = false)
    {
        var (parent, name) = OpenParent(relativePath, create: false);
        try
        {
            var handle = SecureNativeFileSystem.OpenFile(parent.Handle, name, writableMetadata, create: false);
            return new SecureWatchFile(parent, name, handle, writableMetadata);
        }
        catch
        {
            parent.Dispose();
            throw;
        }
    }

    public SecureDownloadLease CreateDownload(string relativePath)
    {
        var (parent, name) = OpenParent(relativePath, create: true);
        try
        {
            return new SecureDownloadLease(parent, name);
        }
        catch
        {
            parent.Dispose();
            throw;
        }
    }

    public void CheckWritable(string relativeDirectory)
    {
        using var probe = CreateDownload(Path.Combine(relativeDirectory, "probe-" + Guid.NewGuid().ToString("N")));
    }

    public bool FileExists(string relativePath) => Exists(relativePath, directory: false);
    public bool DirectoryExists(string relativePath) => Exists(relativePath, directory: true);

    public void DeleteFile(string relativePath)
    {
        try
        {
            using var file = OpenRead(relativePath);
            file.Delete();
        }
        catch (FileNotFoundException) { }
        catch (DirectoryNotFoundException) { }
    }

    public void EnsureDirectory(string relativePath)
    {
        using var chain = OpenDirectory(relativePath, create: true);
    }

    public void RenameDirectory(string oldRelativePath, string newRelativePath)
    {
        var (source, oldName) = OpenParent(oldRelativePath, create: false);
        using (source)
        {
            var (destination, newName) = OpenParent(newRelativePath, create: false);
            using (destination)
            {
                SecureNativeFileSystem.RenameDirectory(source.Handle, oldName, destination.Handle, newName, source.Transactions);
            }
        }
    }

    public IEnumerable<string> EnumerateFiles(bool recursive)
    {
        using var directory = OpenDirectory("", create: false);
        foreach (var path in Enumerate(directory.Handle, "", recursive)) yield return path;
    }

    private static IEnumerable<string> Enumerate(SafeFileHandle directory, string prefix, bool recursive)
    {
        foreach (var name in SecureNativeFileSystem.EnumerateNames(directory))
        {
            if (name is "." or ".." || IsInternalPath(name)) continue;
            var relative = string.IsNullOrEmpty(prefix) ? name : Path.Combine(prefix, name);
            SecureFileMetadata metadata;
            try
            {
                metadata = SecureNativeFileSystem.GetEntryMetadata(directory, name);
            }
            catch (FileNotFoundException) { continue; }
            catch (DirectoryNotFoundException) { continue; }
            if (metadata.IsLink) throw new IOException("Enumeration encountered a linked entry; the source snapshot is incomplete.");
            if (metadata.IsDirectory)
            {
                if (!recursive) continue;
                SafeFileHandle child;
                try { child = SecureNativeFileSystem.OpenDirectory(directory, name, create: false); }
                catch (FileNotFoundException) { continue; }
                catch (DirectoryNotFoundException) { continue; }
                using (child)
                {
                    foreach (var item in Enumerate(child, relative, recursive)) yield return item;
                }
            }
            else if (metadata.IsRegularFile)
            {
                yield return relative;
            }
        }
    }

    private bool Exists(string relativePath, bool directory)
    {
        try
        {
            if (directory && (string.IsNullOrEmpty(relativePath) || relativePath == "."))
            {
                using var root = OpenDirectory("", create: false);
                return directory;
            }
            var (parent, name) = OpenParent(relativePath, create: false);
            using (parent)
            {
                var metadata = SecureNativeFileSystem.GetEntryMetadata(parent.Handle, name);
                if (metadata.IsLink) throw new IOException("Linked entries are not authorized within a watch root.");
                return directory ? metadata.IsDirectory : metadata.IsRegularFile;
            }
        }
        catch (FileNotFoundException) { return false; }
        catch (DirectoryNotFoundException) { return false; }
    }

    private (SecureDirectoryChain Parent, string Name) OpenParent(string relativePath, bool create)
    {
        var components = ValidateRelativePath(relativePath);
        if (components.Length == 0) throw new ArgumentException("A file or child directory name is required.", nameof(relativePath));
        return (OpenDirectory(components[..^1], create), components[^1]);
    }

    private SecureDirectoryChain OpenDirectory(string relativePath, bool create) => OpenDirectory(ValidateRelativePath(relativePath), create);

    private SecureDirectoryChain OpenDirectory(string[] components, bool create)
    {
        var chain = new SecureDirectoryChain(SecureNativeFileSystem.Duplicate(_handle), _transactions);
        try
        {
            foreach (var component in components)
                chain.Add(SecureNativeFileSystem.OpenDirectory(chain.Handle, component, create));
            return chain;
        }
        catch
        {
            chain.Dispose();
            throw;
        }
    }

    internal static string[] ValidateRelativePath(string path)
    {
        ArgumentNullException.ThrowIfNull(path);
        if (Path.IsPathRooted(path) || path.Contains('\0') || IsInternalPath(path))
            throw new IOException("The path must be relative to the authorized watch root.");
        if (path is "" or ".") return [];
        var components = path.Split(Path.DirectorySeparatorChar);
        if (components.Any(component => component is "" or "." or ".."
            || (OperatingSystem.IsWindows() && (component.Contains(':') || component.Contains('/') || component.EndsWith(' ') || component.EndsWith('.')))))
            throw new IOException("The path contains an unsupported component.");
        return components;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _handle.Dispose();
        _transactions.Release();
    }
}

internal sealed class SecureDirectoryChain : IDisposable
{
    private readonly List<SafeFileHandle> _handles;
    private bool _disposed;
    public SecureTransactionPool Transactions { get; }
    public SecureDirectoryChain(SafeFileHandle root, SecureTransactionPool transactions)
    {
        _handles = [root];
        Transactions = transactions;
        try { transactions.AddReference(); }
        catch { root.Dispose(); throw; }
    }
    public SafeFileHandle Handle => _handles[^1];
    public void Add(SafeFileHandle handle) => _handles.Add(handle);
    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        for (var i = _handles.Count - 1; i >= 0; i--) _handles[i].Dispose();
        Transactions.Release();
    }
}

internal readonly record struct SecureFileMetadata(long Length, DateTime CreationTimeUtc, DateTime LastWriteTimeUtc,
    ulong Volume, ulong FileId, uint LinkCount, bool IsDirectory, bool IsRegularFile, bool IsLink, ulong FileIdHigh = 0)
{
    public bool SameIdentity(SecureFileMetadata other) => Volume == other.Volume && FileId == other.FileId && FileIdHigh == other.FileIdHigh;
}
