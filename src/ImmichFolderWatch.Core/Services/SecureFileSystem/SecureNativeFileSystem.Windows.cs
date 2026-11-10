using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace ImmichFolderWatch.Core.Services;

internal static partial class SecureNativeFileSystem
{
    private const uint DirectoryAccess = 0x100081; // SYNCHRONIZE | FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES
    private const uint DeleteAccess = 0x10000;
    private const uint OpenReparsePoint = 0x200000;
    private const uint SynchronousIo = 0x20;
    private static readonly object WindowsEnumerationLock = new();

    private static SafeFileHandle WindowsOpenRoot(string path)
    {
        var handle = WindowsCreateFile(path, DirectoryAccess, 3, IntPtr.Zero, 3, 0x02000000 | 0x00200000, IntPtr.Zero);
        if (handle.IsInvalid) { var error = WindowsError("Open watch root"); handle.Dispose(); throw error; }
        try
        {
            var metadata = WindowsMetadata(handle);
            if (!metadata.IsDirectory || metadata.IsLink) throw new IOException("The watch root must be a real directory.");
            return handle;
        }
        catch { handle.Dispose(); throw; }
    }

    private static SafeFileHandle WindowsDuplicate(SafeFileHandle handle)
    {
        var process = WindowsGetCurrentProcess();
        if (!WindowsDuplicateHandle(process, handle, process, out var copy, 0, false, 2))
            throw WindowsError("Duplicate authorized directory");
        return copy;
    }

    private static SafeFileHandle WindowsOpenDirectory(SafeFileHandle parent, string name, bool create)
    {
        var handle = WindowsOpenRelative(parent, name, DirectoryAccess, 3, create ? 3u : 1u, 1 | SynchronousIo | OpenReparsePoint);
        try
        {
            var metadata = WindowsMetadata(handle);
            if (!metadata.IsDirectory || metadata.IsLink) throw new IOException("Linked watch directories are not authorized.");
            return handle;
        }
        catch { handle.Dispose(); throw; }
    }

    private static SafeFileHandle WindowsOpenFile(SafeFileHandle parent, string name, bool writableMetadata, bool create)
    {
        var access = create ? 0xc0010000u : 0x80100000u | (writableMetadata ? 0x100u : 0u);
        // Read leases allow replacement of their names, but retain the file identity. Private
        // staged files deny every competing open until handle-based publication and disposal.
        var handle = WindowsOpenRelative(parent, name, access, create ? 0u : 7u, create ? 2u : 1u,
            SynchronousIo | OpenReparsePoint | 0x40); // FILE_NON_DIRECTORY_FILE
        try
        {
            RequireRegularFile(WindowsMetadata(handle));
            return handle;
        }
        catch { handle.Dispose(); throw; }
    }

    private static SecureFileMetadata WindowsEntryMetadata(SafeFileHandle parent, string name)
    {
        using var entry = WindowsOpenRelative(parent, name, 0x100080, 7, 1, SynchronousIo | OpenReparsePoint);
        return WindowsMetadata(entry);
    }

    private static SecureFileMetadata WindowsMetadata(SafeFileHandle handle)
    {
        if (!WindowsGetFileInformation(handle, out var information)) throw WindowsError("Read authorized file metadata");
        var directory = (information.Attributes & 0x10) != 0;
        var link = (information.Attributes & 0x400) != 0;
        var identity = WindowsIdentity(handle, information);
        return new SecureFileMetadata(checked((long)(((ulong)information.SizeHigh << 32) | information.SizeLow)),
            DateTime.FromFileTimeUtc(((long)information.CreatedHigh << 32) | information.CreatedLow),
            DateTime.FromFileTimeUtc(((long)information.ModifiedHigh << 32) | information.ModifiedLow),
            identity.VolumeSerial, identity.Low,
            information.LinkCount, directory, !directory && WindowsGetFileType(handle) == 1, link, identity.High);
    }

    private static WindowsFileId WindowsIdentity(SafeFileHandle handle, WindowsFileInformation legacy)
    {
        if (WindowsGetFileId(handle, 18, out var identity, 24)) return identity; // FileIdInfo
        var fileSystem = new StringBuilder(32);
        if (!WindowsGetVolumeInformation(handle, null, 0, out _, out _, out _, fileSystem, fileSystem.Capacity))
            throw WindowsError("Verify filesystem identity support");
        // ReFS requires its complete 128-bit identity. FAT-family filesystems expose only
        // the documented legacy file index; renames can change that index (fail closed).
        if (!new[] { "FAT", "FAT32", "exFAT" }.Contains(fileSystem.ToString(), StringComparer.OrdinalIgnoreCase))
            throw new IOException("The filesystem cannot report an unambiguous supported file identity.");
        return new WindowsFileId
        {
            VolumeSerial = legacy.VolumeSerial,
            Low = ((ulong)legacy.FileIndexHigh << 32) | legacy.FileIndexLow,
        };
    }

    private static IReadOnlyList<string> WindowsEnumerate(SafeFileHandle directory)
    {
        lock (WindowsEnumerationLock)
        {
            const int capacity = 65536;
            var buffer = Marshal.AllocHGlobal(capacity);
            try
            {
                var names = new List<string>();
                var restart = true;
                while (true)
                {
                    if (!WindowsGetFileInformationEx(directory, restart ? 11 : 10, buffer, capacity))
                    {
                        if (Marshal.GetLastPInvokeError() == 18) return names;
                        throw WindowsError("Enumerate authorized directory");
                    }
                    restart = false;
                    var offset = 0;
                    while (true)
                    {
                        if (offset < 0 || offset > capacity - 104) throw new IOException("Invalid directory enumeration metadata.");
                        var item = buffer + offset;
                        var next = Marshal.ReadInt32(item, 0);
                        var length = Marshal.ReadInt32(item, 60);
                        if (length < 0 || length % 2 != 0 || length > capacity - offset - 104)
                            throw new IOException("Invalid directory entry name length.");
                        names.Add(Marshal.PtrToStringUni(item + 104, length / 2)!);
                        if (next == 0) break;
                        if (next < 104 || next > capacity - offset) throw new IOException("Invalid directory entry offset.");
                        offset += next;
                    }
                }
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }
    }

    private static (string Name, SafeFileHandle Handle) WindowsCreatePrivateDirectory(SafeFileHandle parent)
    {
        var name = SecureWatchRoot.InternalPrefix + Guid.NewGuid().ToString("N");
        var handle = WindowsOpenRelative(parent, name, DirectoryAccess | DeleteAccess, 3, 2, 1 | SynchronousIo | OpenReparsePoint);
        try
        {
            var metadata = WindowsMetadata(handle);
            if (!metadata.IsDirectory || metadata.IsLink) throw new IOException("Invalid media transaction directory.");
            return (name, handle);
        }
        catch { handle.Dispose(); throw; }
    }

    private static void WindowsDeleteAuthorizedFile(SafeFileHandle handle)
    {
        // ReOpenFile targets the same filesystem object, not a path which might now name another file.
        using var deletion = WindowsReOpenFile(handle, DeleteAccess, 7, 0);
        if (deletion.IsInvalid) throw WindowsError("Authorize media deletion");
        WindowsMarkDelete(deletion);
    }

    private static void WindowsDeleteDirectory(SafeFileHandle directory) => WindowsMarkDelete(directory);

    private static void WindowsMarkDelete(SafeFileHandle handle)
    {
        var information = Marshal.AllocHGlobal(1);
        try
        {
            Marshal.WriteByte(information, 1);
            if (!WindowsSetFileInformation(handle, 4, information, 1)) throw WindowsError("Delete authorized file identity");
        }
        finally { Marshal.FreeHGlobal(information); }
    }

    private static void WindowsRenameHandle(SafeFileHandle file, SafeFileHandle destination, string name)
    {
        var bytes = Encoding.Unicode.GetBytes(name);
        var rootOffset = IntPtr.Size == 8 ? 8 : 4;
        var lengthOffset = rootOffset + IntPtr.Size;
        var nameOffset = lengthOffset + 4;
        var size = nameOffset + bytes.Length + 2;
        var buffer = Marshal.AllocHGlobal(size);
        var added = false;
        destination.DangerousAddRef(ref added);
        try
        {
            Marshal.Copy(new byte[size], 0, buffer, size);
            Marshal.WriteIntPtr(buffer, rootOffset, destination.DangerousGetHandle());
            Marshal.WriteInt32(buffer, lengthOffset, bytes.Length);
            Marshal.Copy(bytes, 0, buffer + nameOffset, bytes.Length);
            // ReplaceIfExists stays false, preserving any destination created concurrently.
            if (!WindowsSetFileInformation(file, 3, buffer, (uint)size)) throw WindowsError("Publish authorized file without replacement");
        }
        finally
        {
            if (added) destination.DangerousRelease();
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static void WindowsRenameDirectory(SafeFileHandle source, string name, SafeFileHandle destination, string destinationName, SecureTransactionPool transactions)
    {
        using var directory = WindowsOpenRelative(source, name, DirectoryAccess | DeleteAccess, 3, 1, 1 | SynchronousIo | OpenReparsePoint);
        var metadata = WindowsMetadata(directory);
        if (!metadata.IsDirectory || metadata.IsLink) throw new IOException("Linked watch directories cannot be moved.");
        transactions.Hooks?.DirectoryAuthorizedBeforeMove?.Invoke();
        WindowsRenameHandle(directory, destination, destinationName);
    }

    private static void WindowsSetTimestamps(SafeFileHandle file, DateTime createdUtc, DateTime modifiedUtc)
    {
        var created = createdUtc.ToUniversalTime().ToFileTimeUtc();
        var modified = modifiedUtc.ToUniversalTime().ToFileTimeUtc();
        if (!WindowsSetFileTime(file, ref created, IntPtr.Zero, ref modified)) throw WindowsError("Set authorized file timestamps");
    }

    private static long WindowsFreeSpace(SafeFileHandle file)
    {
        var status = WindowsQueryVolumeInformation(file, out _, out var information, 32, 7); // FileFsFullSizeInformation
        if (status < 0) throw WindowsNtError("Read authorized filesystem space", status);
        if (information.AvailableAllocationUnits < 0 || information.BytesPerSector == 0 || information.SectorsPerAllocationUnit == 0)
            throw new IOException("The filesystem did not report available storage.");
        return checked(information.AvailableAllocationUnits * information.BytesPerSector * information.SectorsPerAllocationUnit);
    }

    private static SafeFileHandle WindowsOpenRelative(SafeFileHandle parent, string name, uint access, uint sharing, uint disposition, uint options)
    {
        var nameBytes = checked((ushort)(name.Length * 2));
        var text = Marshal.StringToHGlobalUni(name);
        var unicode = new WindowsUnicodeString { Length = nameBytes, MaximumLength = nameBytes, Buffer = text };
        var unicodePointer = Marshal.AllocHGlobal(Marshal.SizeOf<WindowsUnicodeString>());
        var added = false;
        parent.DangerousAddRef(ref added);
        try
        {
            Marshal.StructureToPtr(unicode, unicodePointer, false);
            var attributes = new WindowsObjectAttributes
            {
                Length = Marshal.SizeOf<WindowsObjectAttributes>(), RootDirectory = parent.DangerousGetHandle(),
                ObjectName = unicodePointer, Attributes = 0x40,
            };
            var status = WindowsNtCreateFile(out var handle, access, ref attributes, out _, IntPtr.Zero,
                0x80, sharing, disposition, options, IntPtr.Zero, 0);
            if (status < 0) { handle?.Dispose(); throw WindowsNtError("Open handle-relative watch entry", status); }
            return handle;
        }
        finally
        {
            if (added) parent.DangerousRelease();
            Marshal.FreeHGlobal(unicodePointer);
            Marshal.FreeHGlobal(text);
        }
    }

    private static IOException WindowsNtError(string operation, int status) => NativeError(operation, checked((int)WindowsStatusToError(status)), windows: true);
    private static IOException WindowsError(string operation) => NativeError(operation, Marshal.GetLastPInvokeError(), windows: true);

    [StructLayout(LayoutKind.Sequential)]
    private struct WindowsUnicodeString { public ushort Length; public ushort MaximumLength; public IntPtr Buffer; }
    [StructLayout(LayoutKind.Sequential)]
    private struct WindowsObjectAttributes
    {
        public int Length; public IntPtr RootDirectory; public IntPtr ObjectName; public uint Attributes;
        public IntPtr SecurityDescriptor; public IntPtr SecurityQualityOfService;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct WindowsIoStatusBlock { public IntPtr Status; public UIntPtr Information; }
    [StructLayout(LayoutKind.Sequential)]
    private struct WindowsFileInformation
    {
        public uint Attributes, CreatedLow, CreatedHigh, AccessedLow, AccessedHigh, ModifiedLow, ModifiedHigh;
        public uint VolumeSerial, SizeHigh, SizeLow, LinkCount, FileIndexHigh, FileIndexLow;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct WindowsFileId { public ulong VolumeSerial, Low, High; }
    [StructLayout(LayoutKind.Sequential)]
    private struct WindowsVolumeSpace
    {
        public long TotalAllocationUnits, AvailableAllocationUnits, ActualAvailableAllocationUnits;
        public uint SectorsPerAllocationUnit, BytesPerSector;
    }
    [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle WindowsCreateFile(string path, uint access, uint sharing, IntPtr security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", EntryPoint = "GetCurrentProcess")] private static extern IntPtr WindowsGetCurrentProcess();
    [DllImport("kernel32.dll", EntryPoint = "DuplicateHandle", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool WindowsDuplicateHandle(IntPtr sourceProcess, SafeFileHandle source, IntPtr targetProcess, out SafeFileHandle target, uint access, [MarshalAs(UnmanagedType.Bool)] bool inherit, uint options);
    [DllImport("kernel32.dll", EntryPoint = "GetFileInformationByHandle", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool WindowsGetFileInformation(SafeFileHandle file, out WindowsFileInformation information);
    [DllImport("kernel32.dll", EntryPoint = "GetFileInformationByHandleEx", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool WindowsGetFileInformationEx(SafeFileHandle file, int informationClass, IntPtr information, uint size);
    [DllImport("kernel32.dll", EntryPoint = "GetFileInformationByHandleEx", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool WindowsGetFileId(SafeFileHandle file, int informationClass, out WindowsFileId information, uint size);
    [DllImport("kernel32.dll", EntryPoint = "GetVolumeInformationByHandleW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool WindowsGetVolumeInformation(SafeFileHandle file, StringBuilder? volumeName, int volumeNameLength,
        out uint serial, out uint maximumComponentLength, out uint flags, StringBuilder fileSystemName, int fileSystemNameLength);
    [DllImport("kernel32.dll", EntryPoint = "GetFileType", SetLastError = true)] private static extern uint WindowsGetFileType(SafeFileHandle file);
    [DllImport("kernel32.dll", EntryPoint = "ReOpenFile", SetLastError = true)] private static extern SafeFileHandle WindowsReOpenFile(SafeFileHandle original, uint access, uint sharing, uint flags);
    [DllImport("kernel32.dll", EntryPoint = "SetFileInformationByHandle", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool WindowsSetFileInformation(SafeFileHandle file, int informationClass, IntPtr information, uint size);
    [DllImport("kernel32.dll", EntryPoint = "SetFileTime", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool WindowsSetFileTime(SafeFileHandle file, ref long created, IntPtr accessed, ref long modified);
    [DllImport("ntdll.dll", EntryPoint = "NtCreateFile")]
    private static extern int WindowsNtCreateFile(out SafeFileHandle handle, uint access, ref WindowsObjectAttributes attributes, out WindowsIoStatusBlock status,
        IntPtr allocationSize, uint fileAttributes, uint sharing, uint disposition, uint options, IntPtr extendedAttributes, uint extendedAttributesLength);
    [DllImport("ntdll.dll", EntryPoint = "RtlNtStatusToDosError")] private static extern uint WindowsStatusToError(int status);
    [DllImport("ntdll.dll", EntryPoint = "NtQueryVolumeInformationFile")]
    private static extern int WindowsQueryVolumeInformation(SafeFileHandle file, out WindowsIoStatusBlock status, out WindowsVolumeSpace information, uint length, int informationClass);
}
