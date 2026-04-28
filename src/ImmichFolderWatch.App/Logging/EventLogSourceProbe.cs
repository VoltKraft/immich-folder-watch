using System;
using System.Diagnostics;
using System.Runtime.Versioning;
using ImmichFolderWatch.App.Shared.Resources;

namespace ImmichFolderWatch.App.Logging;

[SupportedOSPlatform("windows")]
internal static class EventLogSourceProbe
{
    public static bool TryEnsureSource(out string? failureReason)
    {
        try
        {
            if (!EventLog.SourceExists(EventLogConstants.SourceName))
            {
                failureReason = Strings.Op_EventLogSourceMissing;
                return false;
            }

            // The source must be registered under our dedicated log, not under Application.
            // If it's mismatched, EventLog.WriteEntry throws and the underlying provider
            // silently swallows it — surfaces here instead as a clean fallback to file logging.
            var registeredLog = EventLog.LogNameFromSourceName(EventLogConstants.SourceName, ".");
            if (!string.Equals(registeredLog, EventLogConstants.LogName, StringComparison.OrdinalIgnoreCase))
            {
                failureReason = string.Format(
                    Strings.Op_EventLogSourceMisalignedFormat,
                    EventLogConstants.SourceName,
                    registeredLog,
                    EventLogConstants.LogName);
                return false;
            }

            failureReason = null;
            return true;
        }
        catch (Exception ex)
        {
            failureReason = $"{Strings.Op_EventLogSourceMissing} ({ex.Message})";
            return false;
        }
    }
}
