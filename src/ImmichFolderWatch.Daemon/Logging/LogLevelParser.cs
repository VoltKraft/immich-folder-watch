using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Daemon.Logging;

internal static class LogLevelParser
{
    public static LogLevel Parse(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return LogLevel.Information;
        }

        return Enum.TryParse<LogLevel>(value, ignoreCase: true, out var parsed)
            ? parsed
            : LogLevel.Information;
    }
}
