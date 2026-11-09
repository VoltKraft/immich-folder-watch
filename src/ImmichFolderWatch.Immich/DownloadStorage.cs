using System.ComponentModel;
using System.Runtime.InteropServices;

namespace ImmichFolderWatch.Immich;

internal static class DownloadStorage
{
    public static Func<long> CreateFreeSpaceReader(string directory)
    {
        if (OperatingSystem.IsWindows())
        {
            // Query the destination itself: drive-letter enumeration misses UNC
            // shares and may report the wrong volume for a mounted directory.
            var queryPath = Path.EndsInDirectorySeparator(directory) ? directory : directory + Path.DirectorySeparatorChar;
            return () =>
            {
                if (!GetDiskFreeSpaceExW(queryPath, out var available, out _, out _))
                {
                    throw new IOException("Cannot determine available storage for the download.", new Win32Exception(Marshal.GetLastWin32Error()));
                }

                return checked((long)available);
            };
        }

        var drive = DriveInfo.GetDrives()
            .Where(item => directory.Equals(Path.TrimEndingDirectorySeparator(item.Name), StringComparison.Ordinal)
                || directory.StartsWith(Path.EndsInDirectorySeparator(item.Name) ? item.Name : item.Name + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            .OrderByDescending(item => item.Name.Length)
            .FirstOrDefault() ?? throw new IOException("Cannot determine available storage for the download.");
        return () => drive.AvailableFreeSpace;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetDiskFreeSpaceExW(string directory, out ulong available, out ulong total, out ulong totalFree);
}
