using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace ImmichFolderWatch.Core.Platform;

/// <summary>
/// Opens a private Linux directory without following links. Operations stay relative to
/// its descriptor, so renaming a parent cannot redirect a secret-bearing write.
/// </summary>
[SupportedOSPlatform("linux")]
public sealed class LinuxPrivateDirectory : IDisposable
{
    // ARM64 uses the ARM open flags rather than the asm-generic O_DIRECTORY/O_NOFOLLOW values.
    private static int NoFollowFlag => RuntimeInformation.ProcessArchitecture switch
    {
        Architecture.X64 => 0x20000,
        Architecture.Arm64 => 0x8000,
        _ => throw new PlatformNotSupportedException("Private directories require Linux x64 or ARM64."),
    };
    private static int DirectoryFlags => (RuntimeInformation.ProcessArchitecture == Architecture.Arm64 ? 0x4000 : 0x10000)
        | NoFollowFlag | 0x80000; // O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    private const uint OwnerDirectoryMode = 0x1c0; // 0700
    private const uint OwnerFileMode = 0x180; // 0600
    private const uint StatMask = 0xb; // STATX_TYPE | STATX_MODE | STATX_UID
    private readonly SafeFileHandle _handle;

    private LinuxPrivateDirectory(SafeFileHandle handle) => _handle = handle;

    /// <summary>
    /// Creates missing components with mode 0700, rejects links and untrusted writable
    /// ancestors, verifies effective-UID ownership, and restricts the final directory to 0700.
    /// Existing directories owned by another user are never chmod'ed.
    /// </summary>
    public static LinuxPrivateDirectory Open(string path)
    {
        var fullPath = Path.GetFullPath(path);
        var components = fullPath.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (components.Length == 0)
        {
            throw new IOException("The filesystem root cannot be used as a private application directory.");
        }

        var current = OpenDirectory(-100, "/"); // AT_FDCWD
        try
        {
            for (var i = 0; i < components.Length; i++)
            {
                ValidateAncestor(current);
                var descriptor = OpenAt(current, components[i], DirectoryFlags, 0);
                if (descriptor < 0 && Marshal.GetLastPInvokeError() == 2) // ENOENT
                {
                    if (MakeDirectoryAt(current, components[i], OwnerDirectoryMode) != 0
                        && Marshal.GetLastPInvokeError() != 17) // EEXIST from a concurrent startup
                    {
                        throw IoError("Cannot create private application directory");
                    }
                    descriptor = OpenAt(current, components[i], DirectoryFlags, 0);
                }
                if (descriptor < 0)
                {
                    throw IoError("Cannot open private application directory without following links");
                }
                var next = new SafeFileHandle((IntPtr)descriptor, ownsHandle: true);
                current.Dispose();
                current = next;
            }

            var metadata = ReadMetadata(current, "", 0x1000); // AT_EMPTY_PATH
            if (metadata.UserId != GetEffectiveUserId())
            {
                throw new IOException("The private application directory belongs to another user.");
            }
            if (ChangeMode(current, OwnerDirectoryMode) != 0)
            {
                throw IoError("Cannot restrict private application directory permissions");
            }
            return new LinuxPrivateDirectory(current);
        }
        catch
        {
            current.Dispose();
            throw;
        }
    }

    /// <summary>Atomically replaces a regular, current-user-owned file with a flushed 0600 file.</summary>
    public async Task WriteTextAtomicallyAsync(string name, string text, CancellationToken cancellationToken)
    {
        ValidateName(name);
        ValidateExistingFile(name);
        var temporaryName = $".{name}.{Guid.NewGuid():N}.tmp";
        // O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC
        var descriptor = OpenAt(_handle, temporaryName, 1 | 0x40 | 0x80 | NoFollowFlag | 0x80000, OwnerFileMode);
        if (descriptor < 0)
        {
            throw IoError("Cannot create private configuration file");
        }
        try
        {
            using (var handle = new SafeFileHandle((IntPtr)descriptor, ownsHandle: true))
            await using (var stream = new FileStream(handle, FileAccess.Write))
            {
                await stream.WriteAsync(Encoding.UTF8.GetBytes(text), cancellationToken).ConfigureAwait(false);
                stream.Flush(flushToDisk: true);
            }
            cancellationToken.ThrowIfCancellationRequested();
            ValidateExistingFile(name);
            if (RenameAt(_handle, temporaryName, _handle, name) != 0)
            {
                throw IoError("Cannot replace private configuration file");
            }
        }
        finally
        {
            UnlinkAt(_handle, temporaryName, 0);
        }
    }

    public void Dispose() => _handle.Dispose();

    private void ValidateExistingFile(string name)
    {
        if (StatAt(_handle, name, 0x100, StatMask, out var metadata) != 0) // AT_SYMLINK_NOFOLLOW
        {
            if (Marshal.GetLastPInvokeError() == 2)
            {
                return;
            }
            throw IoError("Cannot inspect existing configuration file");
        }
        if ((metadata.Mask & StatMask) != StatMask || metadata.UserId != GetEffectiveUserId()
            || (metadata.Mode & 0xf000) != 0x8000)
        {
            throw new IOException("The configuration file must be a regular file owned by the current user.");
        }
    }

    private static void ValidateAncestor(SafeFileHandle handle)
    {
        var metadata = ReadMetadata(handle, "", 0x1000);
        if (metadata.UserId != 0 && metadata.UserId != GetEffectiveUserId())
        {
            throw new IOException("An application directory ancestor belongs to another user.");
        }
        // A root/current-user-owned sticky directory (for example /tmp) protects owned children.
        if ((metadata.Mode & 0x12) != 0 && (metadata.Mode & 0x200) == 0)
        {
            throw new IOException("An application directory ancestor is writable by another user.");
        }
    }

    private static Statx ReadMetadata(SafeFileHandle handle, string name, int flags)
    {
        if (StatAt(handle, name, flags, StatMask, out var metadata) != 0)
        {
            throw IoError("Cannot verify application directory ownership");
        }
        if ((metadata.Mask & StatMask) != StatMask)
        {
            throw new IOException("The filesystem cannot verify application directory ownership and permissions.");
        }
        return metadata;
    }

    private static SafeFileHandle OpenDirectory(int parent, string name)
    {
        var descriptor = OpenAtRaw(parent, name, DirectoryFlags, 0);
        return descriptor >= 0
            ? new SafeFileHandle((IntPtr)descriptor, ownsHandle: true)
            : throw IoError("Cannot open application directory");
    }

    private static void ValidateName(string name)
    {
        if (string.IsNullOrWhiteSpace(name) || name is "." or ".." || name.Contains('/') || name.Contains('\0'))
        {
            throw new ArgumentException("A single filename is required.", nameof(name));
        }
    }

    private static IOException IoError(string message) => new(message, new Win32Exception(Marshal.GetLastPInvokeError()));

    // Linux statx has a fixed ABI shared by x86_64 and aarch64; unused fields remain reserved.
    [StructLayout(LayoutKind.Explicit, Size = 256)]
    private struct Statx
    {
        [FieldOffset(0)] public uint Mask;
        [FieldOffset(20)] public uint UserId;
        [FieldOffset(28)] public ushort Mode;
    }

    [DllImport("libc", EntryPoint = "openat", SetLastError = true)]
    private static extern int OpenAt(SafeFileHandle directory, string path, int flags, uint mode);
    [DllImport("libc", EntryPoint = "openat", SetLastError = true)]
    private static extern int OpenAtRaw(int directory, string path, int flags, uint mode);
    [DllImport("libc", EntryPoint = "mkdirat", SetLastError = true)]
    private static extern int MakeDirectoryAt(SafeFileHandle directory, string path, uint mode);
    [DllImport("libc", EntryPoint = "statx", SetLastError = true)]
    private static extern int StatAt(SafeFileHandle directory, string path, int flags, uint mask, out Statx metadata);
    [DllImport("libc", EntryPoint = "fchmod", SetLastError = true)]
    private static extern int ChangeMode(SafeFileHandle descriptor, uint mode);
    [DllImport("libc", EntryPoint = "renameat", SetLastError = true)]
    private static extern int RenameAt(SafeFileHandle oldDirectory, string oldPath, SafeFileHandle newDirectory, string newPath);
    [DllImport("libc", EntryPoint = "unlinkat", SetLastError = true)]
    private static extern int UnlinkAt(SafeFileHandle directory, string path, int flags);
    [DllImport("libc", EntryPoint = "geteuid")]
    private static extern uint GetEffectiveUserId();
}
