using System.Globalization;

namespace ImmichFolderWatch.Core.Services;

public static class InotifyLimits
{
    public const string MaxUserWatchesProcPath = "/proc/sys/fs/inotify/max_user_watches";

    public const double WarnFraction = 0.5;

    public const double RefuseFraction = 0.95;

    public static long? GetMaxUserWatches() => GetMaxUserWatches(MaxUserWatchesProcPath);

    public static long? GetMaxUserWatches(string procPath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(procPath);

        if (!OperatingSystem.IsLinux())
        {
            return null;
        }

        try
        {
            if (!File.Exists(procPath))
            {
                return null;
            }

            var raw = File.ReadAllText(procPath).Trim();
            return long.TryParse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value)
                ? value
                : null;
        }
        catch
        {
            return null;
        }
    }

    public static int CountWatchedDirectories(string path, bool includeSubdirectories)
    {
        if (string.IsNullOrWhiteSpace(path) || !Directory.Exists(path))
        {
            return 0;
        }

        if (!includeSubdirectories)
        {
            return 1;
        }

        try
        {
            var enumeration = new EnumerationOptions
            {
                RecurseSubdirectories = true,
                IgnoreInaccessible = true,
                AttributesToSkip = FileAttributes.ReparsePoint,
                MatchType = MatchType.Simple,
                ReturnSpecialDirectories = false,
            };

            // Add 1 for the root itself, which is also a watched directory.
            return 1 + Directory.EnumerateDirectories(path, "*", enumeration).Count();
        }
        catch
        {
            return 1;
        }
    }
}
