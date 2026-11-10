using System.ComponentModel;
using Microsoft.Win32.SafeHandles;

namespace ImmichFolderWatch.Core.Services;

internal static partial class SecureNativeFileSystem
{
    private static bool Windows => OperatingSystem.IsWindows();
    private static void RequireSupportedPlatform()
    {
        if (!OperatingSystem.IsLinux() && !OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Secure watch roots require Windows or Linux.");
    }

    public static SafeFileHandle OpenRoot(string path)
    {
        RequireSupportedPlatform();
        return Windows ? WindowsOpenRoot(path) : LinuxOpenRoot(path);
    }
    public static SafeFileHandle Duplicate(SafeFileHandle handle) => Windows ? WindowsDuplicate(handle) : LinuxDuplicate(handle);
    public static SafeFileHandle OpenDirectory(SafeFileHandle parent, string name, bool create) => Windows
        ? WindowsOpenDirectory(parent, name, create) : LinuxOpenDirectory(parent, name, create);
    public static SafeFileHandle OpenFile(SafeFileHandle parent, string name, bool writableMetadata, bool create) => Windows
        ? WindowsOpenFile(parent, name, writableMetadata, create) : LinuxOpenFile(parent, name, create);
    public static SecureFileMetadata GetMetadata(SafeFileHandle handle) => Windows ? WindowsMetadata(handle) : LinuxMetadata(handle);
    public static SecureFileMetadata GetEntryMetadata(SafeFileHandle parent, string name) => Windows
        ? WindowsEntryMetadata(parent, name) : LinuxEntryMetadata(parent, name);
    public static IReadOnlyList<string> EnumerateNames(SafeFileHandle directory) => Windows
        ? WindowsEnumerate(directory) : LinuxEnumerate(directory);
    internal static (string Name, SafeFileHandle Handle) CreateProtectedContainer(SafeFileHandle parent) => LinuxCreatePrivateDirectory(parent);
    public static SecureTransactionDirectory CreateTransaction(SafeFileHandle parent, SecureTransactionPool transactions)
    {
        var container = Windows ? (Name: "", Handle: Duplicate(parent)) : transactions.GetContainer(parent);
        try
        {
            var operation = Windows ? WindowsCreatePrivateDirectory(container.Handle) : LinuxCreatePrivateDirectory(container.Handle);
            return new SecureTransactionDirectory(container.Handle, operation.Name, operation.Handle,
                string.IsNullOrEmpty(container.Name) ? operation.Name : container.Name + "/" + operation.Name);
        }
        catch { container.Handle.Dispose(); throw; }
    }
    public static long GetAvailableFreeSpace(SafeFileHandle file) => Windows ? WindowsFreeSpace(file) : LinuxFreeSpace(file);
    public static void SetTimestamps(SafeFileHandle file, DateTime createdUtc, DateTime modifiedUtc)
    {
        if (GetMetadata(file).LinkCount != 1)
            throw new IOException("Refusing to modify metadata of a file with multiple hard links.");
        if (Windows) WindowsSetTimestamps(file, createdUtc, modifiedUtc);
        else LinuxSetTimestamps(file, modifiedUtc);
    }
    public static void DeleteAuthorizedFile(SafeFileHandle parent, string name, SafeFileHandle file, SecureTransactionPool transactions)
    {
        if (Windows) WindowsDeleteAuthorizedFile(file);
        else LinuxDeleteAuthorizedFile(parent, name, file, transactions);
    }
    public static void DeletePrivateFile(SafeFileHandle parent, string name, SafeFileHandle file)
    {
        if (Windows) WindowsMarkDelete(file);
        else LinuxDeletePrivateFile(parent, name, file);
    }
    public static void RemovePrivateDirectory(SafeFileHandle parent, string name, SafeFileHandle directory)
    {
        if (Windows) WindowsDeleteDirectory(directory);
        else LinuxRemovePrivateDirectory(parent, name, directory);
    }
    public static void PublishFile(SafeFileHandle source, string name, SafeFileHandle file, SafeFileHandle destination, string destinationName)
    {
        if (Windows) WindowsRenameHandle(file, destination, destinationName);
        else LinuxPublishFile(source, name, file, destination, destinationName);
    }
    public static void RenameDirectory(SafeFileHandle source, string name, SafeFileHandle destination, string destinationName, SecureTransactionPool transactions)
    {
        if (Windows) WindowsRenameDirectory(source, name, destination, destinationName, transactions);
        else LinuxRenameDirectory(source, name, destination, destinationName, transactions);
    }

    private static IOException NativeError(string operation, int error, bool windows)
    {
        if ((windows && error is 2 or 3) || (!windows && error == 2))
            return new FileNotFoundException($"{operation}: the authorized entry no longer exists.");
        return new IOException($"{operation} failed.", new Win32Exception(error));
    }

    private static void RequireRegularFile(SecureFileMetadata metadata)
    {
        if (!metadata.IsRegularFile || metadata.IsLink)
            throw new IOException("Only regular non-linked media files are authorized.");
    }
}
