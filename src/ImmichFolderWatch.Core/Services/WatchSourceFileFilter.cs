using System.Text;
using System.Text.RegularExpressions;
using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Core.Services;

public sealed class WatchSourceFileFilter
{
    private readonly string _sourceRoot;
    private readonly HashSet<string> _allowedExtensions;
    private readonly IReadOnlyList<Regex> _excludedDirectoryPatterns;
    private readonly IReadOnlyList<Regex> _excludedFileNamePatterns;

    public WatchSourceFileFilter(WatchSourceSettings source)
        : this(source.Path, source.Extensions, source.ExcludeDirectories, source.ExcludeFileNames)
    {
    }

    public WatchSourceFileFilter(
        string sourceRoot,
        IEnumerable<string> extensions,
        IEnumerable<string>? excludeDirectories = null,
        IEnumerable<string>? excludeFileNames = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceRoot);
        ArgumentNullException.ThrowIfNull(extensions);

        _sourceRoot = Path.GetFullPath(sourceRoot);
        _allowedExtensions = extensions
            .Select(NormalizeExtension)
            .Where(extension => !string.IsNullOrWhiteSpace(extension))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        _excludedDirectoryPatterns = CompileDirectoryPatterns(excludeDirectories);
        _excludedFileNamePatterns = CompileFileNamePatterns(excludeFileNames);
    }

    public bool IsMatch(string filePath)
    {
        if (string.IsNullOrWhiteSpace(filePath) || _allowedExtensions.Count == 0)
        {
            return false;
        }

        var normalizedPath = NormalizeFullPath(filePath);
        if (!HasAllowedExtension(normalizedPath))
        {
            return false;
        }

        var relativeFilePath = GetRelativeFilePath(normalizedPath);
        if (string.IsNullOrWhiteSpace(relativeFilePath))
        {
            return false;
        }

        var fileName = Path.GetFileName(normalizedPath);
        if (MatchesAny(_excludedFileNamePatterns, fileName))
        {
            return false;
        }

        var relativeDirectory = GetRelativeDirectory(relativeFilePath);
        return !MatchesExcludedDirectory(relativeDirectory);
    }

    private bool HasAllowedExtension(string path)
    {
        var extension = NormalizeExtension(Path.GetExtension(path));
        return !string.IsNullOrWhiteSpace(extension) && _allowedExtensions.Contains(extension);
    }

    private bool MatchesExcludedDirectory(string relativeDirectory)
    {
        if (_excludedDirectoryPatterns.Count == 0 || string.IsNullOrWhiteSpace(relativeDirectory))
        {
            return false;
        }

        foreach (var ancestor in EnumerateDirectoryAncestors(relativeDirectory))
        {
            if (MatchesAny(_excludedDirectoryPatterns, ancestor))
            {
                return true;
            }
        }

        return false;
    }

    private string? GetRelativeFilePath(string filePath)
    {
        var relativeFilePath = NormalizeRelativePath(Path.GetRelativePath(_sourceRoot, filePath));
        return relativeFilePath.StartsWith("../", StringComparison.Ordinal)
            || string.Equals(relativeFilePath, "..", StringComparison.Ordinal)
            ? null
            : relativeFilePath;
    }

    private static string GetRelativeDirectory(string relativeFilePath)
    {
        var fileDirectory = Path.GetDirectoryName(relativeFilePath);
        if (string.IsNullOrWhiteSpace(fileDirectory))
        {
            return string.Empty;
        }

        var relativeDirectory = NormalizeRelativePath(fileDirectory);
        if (relativeDirectory is "." or "")
        {
            return string.Empty;
        }

        return relativeDirectory;
    }

    private static IReadOnlyList<string> EnumerateDirectoryAncestors(string relativeDirectory)
    {
        var normalized = NormalizeRelativePath(relativeDirectory);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return Array.Empty<string>();
        }

        var segments = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (segments.Length == 0)
        {
            return Array.Empty<string>();
        }

        var results = new List<string>(segments.Length);
        for (var i = segments.Length; i > 0; i--)
        {
            results.Add(string.Join('/', segments.Take(i)));
        }

        return results;
    }

    private static IReadOnlyList<Regex> CompileDirectoryPatterns(IEnumerable<string>? patterns)
    {
        return (patterns ?? Array.Empty<string>())
            .Where(pattern => !string.IsNullOrWhiteSpace(pattern))
            .Select(pattern => CreateGlobRegex(NormalizeRelativePath(pattern), pathAware: true))
            .ToList();
    }

    private static IReadOnlyList<Regex> CompileFileNamePatterns(IEnumerable<string>? patterns)
    {
        return (patterns ?? Array.Empty<string>())
            .Where(pattern => !string.IsNullOrWhiteSpace(pattern))
            .Select(pattern => CreateGlobRegex(pattern.Trim(), pathAware: false))
            .ToList();
    }

    private static bool MatchesAny(IEnumerable<Regex> patterns, string value)
    {
        return patterns.Any(pattern => pattern.IsMatch(value));
    }

    private static Regex CreateGlobRegex(string pattern, bool pathAware)
    {
        var regexBuilder = new StringBuilder("^");

        for (var i = 0; i < pattern.Length; i++)
        {
            var current = pattern[i];
            if (current == '*')
            {
                var isDoubleStar = i + 1 < pattern.Length && pattern[i + 1] == '*';
                if (isDoubleStar)
                {
                    i++;

                    var hasTrailingSeparator = pathAware
                        && i + 1 < pattern.Length
                        && (pattern[i + 1] == '/' || pattern[i + 1] == '\\');

                    if (hasTrailingSeparator)
                    {
                        i++;
                        regexBuilder.Append("(?:[^/]+/)*");
                    }
                    else
                    {
                        regexBuilder.Append(".*");
                    }

                    continue;
                }

                regexBuilder.Append(pathAware ? "[^/]*" : ".*");
                continue;
            }

            if (current == '?')
            {
                regexBuilder.Append(pathAware ? "[^/]" : ".");
                continue;
            }

            if (pathAware && (current == '/' || current == '\\'))
            {
                regexBuilder.Append('/');
                continue;
            }

            regexBuilder.Append(Regex.Escape(current.ToString()));
        }

        regexBuilder.Append("$");
        return new Regex(
            regexBuilder.ToString(),
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.Compiled);
    }

    private static string NormalizeExtension(string extension)
    {
        if (string.IsNullOrWhiteSpace(extension))
        {
            return string.Empty;
        }

        var trimmed = extension.Trim();
        return trimmed.StartsWith('.')
            ? trimmed.ToLowerInvariant()
            : $".{trimmed.ToLowerInvariant()}";
    }

    private static string NormalizeFullPath(string path)
    {
        try
        {
            return Path.GetFullPath(path);
        }
        catch (Exception)
        {
            return path;
        }
    }

    private static string NormalizeRelativePath(string path)
    {
        return path
            .Trim()
            .Replace('\\', '/')
            .Trim('/');
    }
}
