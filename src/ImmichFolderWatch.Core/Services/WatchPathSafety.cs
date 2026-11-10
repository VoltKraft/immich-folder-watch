namespace ImmichFolderWatch.Core.Services;

/// <summary>
/// Rejects linked entries beneath a configured root, including missing leaf paths.
/// This is a pathname check, not an atomic filesystem authorization primitive:
/// sources must not be writable by an untrusted concurrent principal.
/// </summary>
public static class WatchPathSafety
{
    public static bool IsSafePath(string root, string path, bool allowMissingLeaf = false)
    {
        try
        {
            root = Path.GetFullPath(root);
            path = Path.GetFullPath(path);
            var relative = Path.GetRelativePath(root, path);
            if (Path.IsPathRooted(relative) || relative == ".."
                || relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            {
                return false;
            }

            // The configured root may be a portal mount. Do not reject its trusted
            // ancestors; all entries beneath it (including the root itself) are checked.
            var current = root;
            var segments = relative == "." ? Array.Empty<string>() : relative.Split(Path.DirectorySeparatorChar);
            for (var i = -1; i < segments.Length; i++)
            {
                if (i >= 0)
                {
                    current = Path.Combine(current, segments[i]);
                }

                try
                {
                    if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    {
                        return false;
                    }
                }
                catch (FileNotFoundException) when (allowMissingLeaf && i >= 0)
                {
                    // Continue checking: a dangling symlink may be a later component.
                }
                catch (DirectoryNotFoundException) when (allowMissingLeaf && i >= 0)
                {
                }
            }

            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return false;
        }
    }

    public static EnumerationOptions EnumerationOptions(bool recursive) => new()
    {
        RecurseSubdirectories = recursive,
        AttributesToSkip = FileAttributes.ReparsePoint,
        IgnoreInaccessible = false,
        ReturnSpecialDirectories = false,
    };
}
