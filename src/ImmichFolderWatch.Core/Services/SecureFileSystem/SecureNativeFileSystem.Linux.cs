using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace ImmichFolderWatch.Core.Services;

internal static partial class SecureNativeFileSystem
{
    private static int LinuxNoFollow => RuntimeInformation.ProcessArchitecture switch
    {
        Architecture.X64 => 0x20000,
        Architecture.Arm64 => 0x8000,
        _ => throw new PlatformNotSupportedException("Secure watch roots require Linux x64 or ARM64."),
    };
    private static int LinuxDirectory => RuntimeInformation.ProcessArchitecture == Architecture.Arm64 ? 0x4000 : 0x10000;
    private const int CloseOnExec = 0x80000;
    private const int PathOnly = 0x200000;
    private const uint BasicStat = 0x7ff;

    private static SafeFileHandle LinuxOpenRoot(string path)
    {
        // Only initial root acquisition resolves trusted ancestors, including portal mount paths.
        return LinuxHandle(LinuxOpenAtRaw(-100, path, LinuxDirectory | LinuxNoFollow | CloseOnExec, 0), "Open watch root");
    }

    private static SafeFileHandle LinuxDuplicate(SafeFileHandle handle) =>
        LinuxHandle(LinuxFcntl(handle, 1030, 0), "Duplicate authorized directory"); // F_DUPFD_CLOEXEC

    private static SafeFileHandle LinuxOpenDirectory(SafeFileHandle parent, string name, bool create)
    {
        var descriptor = LinuxOpenAt(parent, name, LinuxDirectory | LinuxNoFollow | CloseOnExec, 0);
        if (descriptor < 0 && Marshal.GetLastPInvokeError() == 2 && create)
        {
            if (LinuxMkdirAt(parent, name, 0x1ed) != 0 && Marshal.GetLastPInvokeError() != 17)
                throw LinuxError("Create watch subdirectory");
            descriptor = LinuxOpenAt(parent, name, LinuxDirectory | LinuxNoFollow | CloseOnExec, 0);
        }
        return LinuxHandle(descriptor, "Open authorized subdirectory");
    }

    private static SafeFileHandle LinuxOpenFile(SafeFileHandle parent, string name, bool create)
    {
        if (create)
        {
            var created = LinuxHandle(LinuxOpenAt(parent, name, 2 | 0x40 | 0x80 | LinuxNoFollow | CloseOnExec, 0x180), "Create staged media");
            try { RequireRegularFile(LinuxMetadata(created)); return created; }
            catch { created.Dispose(); throw; }
        }
        // O_PATH inspects type without opening a device/FIFO. Reopening our own descriptor
        // through procfs keeps the verified inode even if its directory entry is replaced.
        using var identity = LinuxHandle(LinuxOpenAt(parent, name, PathOnly | LinuxNoFollow | CloseOnExec, 0), "Authorize media file");
        RequireRegularFile(LinuxMetadata(identity));
        var success = false;
        identity.DangerousAddRef(ref success);
        try
        {
            var stream = LinuxHandle(LinuxOpenAtRaw(-100, $"/proc/self/fd/{identity.DangerousGetHandle()}", CloseOnExec | 0x800, 0), "Open authorized media stream");
            try
            {
                // Match .NET FileShare semantics: a writer holding FileShare.None must
                // still make readiness checks fail even though this open is handle-relative.
                if (LinuxFlock(stream, 1 | 4) != 0) throw LinuxError("Acquire shared media read lock"); // LOCK_SH | LOCK_NB
                return stream;
            }
            catch { stream.Dispose(); throw; }
        }
        finally { if (success) identity.DangerousRelease(); }
    }

    private static SecureFileMetadata LinuxMetadata(SafeFileHandle handle)
    {
        if (LinuxStatAt(handle, "", 0x1000, BasicStat | 0x800, out var info) != 0)
            throw LinuxError("Read authorized file metadata");
        return ConvertLinuxMetadata(info);
    }

    private static SecureFileMetadata LinuxEntryMetadata(SafeFileHandle parent, string name)
    {
        if (LinuxStatAt(parent, name, 0x100, BasicStat | 0x800, out var info) != 0)
            throw LinuxError("Read authorized entry metadata");
        return ConvertLinuxMetadata(info);
    }

    private static SecureFileMetadata ConvertLinuxMetadata(LinuxStatx info)
    {
        if ((info.Mask & 0x747) != 0x747) // type, mode, link count, inode, size, mtime, ctime
            throw new IOException("The filesystem cannot report secure file identity and metadata.");
        var type = info.Mode & 0xf000;
        var modified = FromUnixTime(info.ModifiedSeconds, info.ModifiedNanoseconds);
        var created = (info.Mask & 0x800) != 0 ? FromUnixTime(info.CreatedSeconds, info.CreatedNanoseconds) : modified;
        return new SecureFileMetadata(checked((long)info.Size), created, modified,
            ((ulong)info.DeviceMajor << 32) | info.DeviceMinor, info.Inode, info.LinkCount,
            type == 0x4000, type == 0x8000, type == 0xa000);
    }

    private static DateTime FromUnixTime(long seconds, uint nanoseconds) => DateTime.UnixEpoch.AddSeconds(seconds).AddTicks(nanoseconds / 100);

    private static IReadOnlyList<string> LinuxEnumerate(SafeFileHandle directory)
    {
        var added = false;
        directory.DangerousAddRef(ref added);
        try
        {
            return Directory.EnumerateFileSystemEntries($"/proc/self/fd/{directory.DangerousGetHandle()}")
                .Select(Path.GetFileName).OfType<string>().ToArray();
        }
        finally { if (added) directory.DangerousRelease(); }
    }

    private static (string Name, SafeFileHandle Handle) LinuxCreatePrivateDirectory(SafeFileHandle parent)
    {
        var name = SecureWatchRoot.InternalPrefix + Guid.NewGuid().ToString("N");
        if (LinuxMkdirAt(parent, name, 0x1c0) != 0) throw LinuxError("Create private media transaction directory");
        var handle = LinuxOpenDirectory(parent, name, create: false);
        try
        {
            if (LinuxStatAt(handle, "", 0x1000, BasicStat, out var info) != 0)
                throw LinuxError("Verify media transaction directory");
            if ((info.Mask & 0xb) != 0xb || info.UserId != LinuxGetEffectiveUserId()
                || (info.Mode & 0xf000) != 0x4000 || (info.Mode & 0x1ff) != 0x1c0)
                throw new IOException("The filesystem must enforce a current-user-owned 0700 media transaction directory.");
            return (name, handle);
        }
        catch
        {
            handle.Dispose();
            // Do not remove an entry whose identity/ownership could not be established.
            throw;
        }
    }

    private static void LinuxPublishFile(SafeFileHandle source, string name, SafeFileHandle file, SafeFileHandle destination, string destinationName)
    {
        if (!LinuxMetadata(file).SameIdentity(LinuxEntryMetadata(source, name)))
            throw new IOException("The staged file identity changed before publication.");
        // The source is in a verified private transaction directory. No hard links are
        // required, so filesystems with protected directories and renameat2 are supported.
        LinuxRenameNoReplace(source, name, destination, destinationName);
    }

    private static void LinuxDeletePrivateFile(SafeFileHandle directory, string name, SafeFileHandle expected)
    {
        var metadata = LinuxEntryMetadata(directory, name);
        if (!metadata.SameIdentity(LinuxMetadata(expected)))
            throw new IOException("The private transaction file identity changed; preserving it for inspection.");
        if (LinuxUnlinkAt(directory, name, 0) != 0) throw LinuxError("Remove private transaction file");
    }

    private static void LinuxDeleteAuthorizedFile(SafeFileHandle parent, string name, SafeFileHandle expected, SecureTransactionPool transactions)
    {
        var identity = LinuxMetadata(expected);
        RequireRegularFile(identity);
        var transaction = CreateTransaction(parent, transactions);
        var quarantine = transaction.Handle;
        var privateName = transaction.DisplayPath;
        var moved = false;
        var preserve = false;
        try
        {
            LinuxRenameNoReplace(parent, name, quarantine, "entry");
            moved = true;
            var quarantined = LinuxEntryMetadata(quarantine, "entry");
            if (!identity.SameIdentity(quarantined) || !quarantined.IsRegularFile || quarantined.IsLink)
            {
                try { LinuxRenameNoReplace(quarantine, "entry", parent, name); moved = false; }
                catch { preserve = true; }
                throw new IOException(preserve
                    ? $"The media entry changed. Its replacement is preserved in {privateName}/entry because the original name is occupied."
                    : "The media entry changed; its replacement was restored without deletion.");
            }
            if (LinuxUnlinkAt(quarantine, "entry", 0) != 0) throw LinuxError("Delete authorized media identity");
            moved = false;
        }
        catch
        {
            if (moved && !preserve)
            {
                try { LinuxRenameNoReplace(quarantine, "entry", parent, name); moved = false; }
                catch { preserve = true; }
            }
            throw;
        }
        finally
        {
            if (preserve || moved) transaction.Preserve();
            transaction.Dispose();
        }
    }

    private static void LinuxRemovePrivateDirectory(SafeFileHandle parent, string name, SafeFileHandle expected)
    {
        try
        {
            if (!LinuxMetadata(expected).SameIdentity(LinuxEntryMetadata(parent, name)))
                throw new IOException("The transaction directory was moved; refusing to remove its replacement.");
            if (LinuxUnlinkAt(parent, name, 0x200) != 0) throw LinuxError("Remove empty media transaction directory");
        }
        catch (FileNotFoundException) { }
    }

    private static void LinuxRenameDirectory(SafeFileHandle source, string name, SafeFileHandle destination, string destinationName, SecureTransactionPool transactions)
    {
        using var authorized = LinuxOpenDirectory(source, name, create: false);
        var expected = LinuxMetadata(authorized);
        transactions.Hooks?.DirectoryAuthorizedBeforeMove?.Invoke();
        var transaction = CreateTransaction(source, transactions);
        var quarantine = transaction.Handle;
        var privateName = transaction.DisplayPath;
        var moved = false;
        var preserve = false;
        try
        {
            LinuxRenameNoReplace(source, name, quarantine, "entry");
            moved = true;
            var actual = LinuxEntryMetadata(quarantine, "entry");
            if (!actual.IsDirectory || actual.IsLink || !actual.SameIdentity(expected))
                throw new IOException("The directory identity changed before its authorized move.");
            LinuxRenameNoReplace(quarantine, "entry", destination, destinationName);
            moved = false;
        }
        catch
        {
            if (moved)
            {
                try { LinuxRenameNoReplace(quarantine, "entry", source, name); moved = false; }
                catch { preserve = true; }
            }
            if (preserve)
                throw new IOException($"The directory move failed; the original entry is preserved in {privateName}/entry because its previous name is occupied.");
            throw;
        }
        finally
        {
            if (preserve || moved) transaction.Preserve();
            transaction.Dispose();
        }
    }

    private static void LinuxRenameNoReplace(SafeFileHandle source, string name, SafeFileHandle destination, string destinationName)
    {
        if (LinuxRenameAt2(source, name, destination, destinationName, 1) != 0)
            throw LinuxError("Atomically move authorized entry without replacement");
    }

    private static void LinuxSetTimestamps(SafeFileHandle file, DateTime modifiedUtc)
    {
        var ticks = modifiedUtc.ToUniversalTime().Ticks - DateTime.UnixEpoch.Ticks;
        var times = new[] { new LinuxTimespec { Nanoseconds = 1073741822 }, new LinuxTimespec
            { Seconds = Math.DivRem(ticks, TimeSpan.TicksPerSecond, out var remainder), Nanoseconds = remainder * 100 } };
        if (times[1].Nanoseconds < 0) { times[1].Seconds--; times[1].Nanoseconds += 1000000000; }
        if (LinuxFutimens(file, times) != 0) throw LinuxError("Set authorized file timestamps");
    }

    private static long LinuxFreeSpace(SafeFileHandle file)
    {
        if (LinuxFstatvfs(file, out var information) != 0) throw LinuxError("Read authorized filesystem space");
        return checked((long)(information.AvailableBlocks * information.FragmentSize));
    }

    private static SafeFileHandle LinuxHandle(int descriptor, string operation) => descriptor >= 0
        ? new SafeFileHandle((IntPtr)descriptor, true) : throw LinuxError(operation);
    private static IOException LinuxError(string operation) => NativeError(operation, Marshal.GetLastPInvokeError(), windows: false);

    [StructLayout(LayoutKind.Explicit, Size = 256)]
    private struct LinuxStatx
    {
        [FieldOffset(0)] public uint Mask;
        [FieldOffset(16)] public uint LinkCount;
        [FieldOffset(20)] public uint UserId;
        [FieldOffset(28)] public ushort Mode;
        [FieldOffset(32)] public ulong Inode;
        [FieldOffset(40)] public ulong Size;
        [FieldOffset(80)] public long CreatedSeconds;
        [FieldOffset(88)] public uint CreatedNanoseconds;
        [FieldOffset(112)] public long ModifiedSeconds;
        [FieldOffset(120)] public uint ModifiedNanoseconds;
        [FieldOffset(136)] public uint DeviceMajor;
        [FieldOffset(140)] public uint DeviceMinor;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct LinuxTimespec { public long Seconds; public long Nanoseconds; }
    [StructLayout(LayoutKind.Explicit, Size = 112)]
    private struct LinuxStatvfs
    {
        [FieldOffset(8)] public ulong FragmentSize;
        [FieldOffset(32)] public ulong AvailableBlocks;
    }
    [DllImport("libc", EntryPoint = "openat", SetLastError = true)] private static extern int LinuxOpenAt(SafeFileHandle parent, string name, int flags, uint mode);
    [DllImport("libc", EntryPoint = "openat", SetLastError = true)] private static extern int LinuxOpenAtRaw(int parent, string name, int flags, uint mode);
    [DllImport("libc", EntryPoint = "flock", SetLastError = true)] private static extern int LinuxFlock(SafeFileHandle handle, int operation);
    [DllImport("libc", EntryPoint = "fcntl", SetLastError = true)] private static extern int LinuxFcntl(SafeFileHandle handle, int command, int value);
    [DllImport("libc", EntryPoint = "mkdirat", SetLastError = true)] private static extern int LinuxMkdirAt(SafeFileHandle parent, string name, uint mode);
    [DllImport("libc", EntryPoint = "statx", SetLastError = true)] private static extern int LinuxStatAt(SafeFileHandle parent, string name, int flags, uint mask, out LinuxStatx info);
    [DllImport("libc", EntryPoint = "renameat2", SetLastError = true)] private static extern int LinuxRenameAt2(SafeFileHandle source, string name, SafeFileHandle destination, string destinationName, uint flags);
    [DllImport("libc", EntryPoint = "unlinkat", SetLastError = true)] private static extern int LinuxUnlinkAt(SafeFileHandle parent, string name, int flags);
    [DllImport("libc", EntryPoint = "geteuid")] private static extern uint LinuxGetEffectiveUserId();
    [DllImport("libc", EntryPoint = "futimens", SetLastError = true)] private static extern int LinuxFutimens(SafeFileHandle handle, [In] LinuxTimespec[] times);
    [DllImport("libc", EntryPoint = "fstatvfs", SetLastError = true)] private static extern int LinuxFstatvfs(SafeFileHandle handle, out LinuxStatvfs information);
}
