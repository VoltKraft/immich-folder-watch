using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

/// <summary>
/// Asks xdg-desktop-portal-Background for permission to keep running
/// after the user closes the main window. On GNOME 46+ the portal
/// surfaces a one-time consent dialog and, once approved, lists the
/// app in the Quick Settings → Background Apps panel — the closest
/// stand-in for a system-tray icon when no AppIndicator extension
/// is installed. On KDE / sway / XFCE the call is a quiet no-op or
/// a quick approval; the app keeps running in either case
/// (Avalonia's dispatcher loop doesn't need this consent — the
/// portal call is purely about the shell-side UX presence).
/// </summary>
public sealed class BackgroundPortalClient
{
    private const string Service = "org.freedesktop.portal.Desktop";
    private const string ObjectPath = "/org/freedesktop/portal/desktop";
    private const string InterfaceName = "org.freedesktop.portal.Background";

    private readonly DBusSession _session;
    private readonly ILogger<BackgroundPortalClient> _logger;
    private int _requested;

    public BackgroundPortalClient(DBusSession session)
        : this(session, NullLogger<BackgroundPortalClient>.Instance)
    {
    }

    public BackgroundPortalClient(DBusSession session, ILogger<BackgroundPortalClient> logger)
    {
        _session = session;
        _logger = logger;
    }

    /// <summary>
    /// Sends a single RequestBackground call to the Desktop portal.
    /// Idempotent for the lifetime of the process — subsequent calls
    /// no-op. Fire-and-forget: we don't subscribe to the Request's
    /// Response signal because the worker stays running regardless
    /// of consent, and the next .desktop launcher click re-shows the
    /// window via the existing single-instance handler.
    /// </summary>
    public Task RequestBackgroundAsync(CancellationToken cancellationToken = default)
    {
        if (Interlocked.CompareExchange(ref _requested, 1, 0) == 1)
        {
            return Task.CompletedTask;
        }

        return SendRequestBackgroundAsync(cancellationToken);
    }

    private async Task SendRequestBackgroundAsync(CancellationToken cancellationToken)
    {
        try
        {
            var connection = await _session.GetAsync(cancellationToken).ConfigureAwait(false);
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(
                destination: Service,
                path: ObjectPath,
                @interface: InterfaceName,
                member: "RequestBackground",
                signature: "sa{sv}",
                flags: MessageFlags.None);

            // parent_window: empty (the close click is the parent context).
            writer.WriteString(string.Empty);

            // options: a{sv}
            var dictStart = writer.WriteDictionaryStart();

            writer.WriteDictionaryEntryStart();
            writer.WriteString("reason");
            writer.WriteVariantString("Watching photo folders for upload to Immich.");

            writer.WriteDictionaryEntryStart();
            writer.WriteString("autostart");
            writer.WriteVariantBool(false);

            writer.WriteDictionaryEntryStart();
            writer.WriteString("background");
            writer.WriteVariantBool(true);

            writer.WriteDictionaryEnd(dictStart);

            var message = writer.CreateMessage();

            // Fire-and-forget: success surfaces only as the Background
            // Apps entry appearing in GNOME's Quick Settings the next
            // time the panel opens. Failure (no portal, user denial)
            // leaves the worker running anyway.
            _ = connection.CallMethodAsync(message, ReadObjectPathReply, this);
            _logger.LogInformation("Background portal: RequestBackground sent.");
        }
        catch (Exception ex)
        {
            _logger.LogDebug(
                ex,
                "Background portal RequestBackground failed; continuing without portal-based shell presence.");
        }
    }

    private static string ReadObjectPathReply(Message message, object? state)
    {
        return message.GetBodyReader().ReadObjectPathAsString();
    }
}
