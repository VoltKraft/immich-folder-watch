using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Core.Logging;

public static class JournaldLoggingExtensions
{
    public static bool IsJournaldDetected()
    {
        return !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FLATPAK_ID"))
            || !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("JOURNAL_STREAM"))
            || !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("INVOCATION_ID"));
    }

    public static ILoggingBuilder AddJournaldConsoleIfDetected(
        this ILoggingBuilder builder,
        bool force = false)
    {
        ArgumentNullException.ThrowIfNull(builder);

        if (force || IsJournaldDetected())
        {
            builder.AddSystemdConsole(options =>
            {
                options.IncludeScopes = true;
                options.UseUtcTimestamp = true;
            });
        }

        return builder;
    }
}
