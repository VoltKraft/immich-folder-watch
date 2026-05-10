using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class DBusNotifier : INotifier
{
    private const string ServiceName = "org.freedesktop.Notifications";
    private const string ObjectPath = "/org/freedesktop/Notifications";
    private const string InterfaceName = "org.freedesktop.Notifications";
    private const string AppName = "Immich Folder Watch";

    private readonly DBusSession _session;
    private readonly ILogger<DBusNotifier> _logger;

    public DBusNotifier(DBusSession session)
        : this(session, NullLogger<DBusNotifier>.Instance)
    {
    }

    public DBusNotifier(DBusSession session, ILogger<DBusNotifier> logger)
    {
        _session = session;
        _logger = logger;
    }

    public async Task ShowAsync(
        string title,
        string body,
        NotificationKind kind = NotificationKind.Info,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var connection = await _session.GetAsync(cancellationToken).ConfigureAwait(false);
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(
                destination: ServiceName,
                path: ObjectPath,
                @interface: InterfaceName,
                member: "Notify",
                signature: "susssasa{sv}i",
                flags: MessageFlags.None);
            writer.WriteString(AppName);
            writer.WriteUInt32(0);
            writer.WriteString(MapIcon(kind));
            writer.WriteString(title);
            writer.WriteString(body);
            writer.WriteArray(Array.Empty<string>());
            writer.WriteDictionary(new Dictionary<string, VariantValue>());
            writer.WriteInt32(-1);
            var message = writer.CreateMessage();
            await connection.CallMethodAsync(message).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to deliver notification: {Title}", title);
        }
    }

    private static string MapIcon(NotificationKind kind) => kind switch
    {
        NotificationKind.Error => "dialog-error",
        NotificationKind.Warning => "dialog-warning",
        _ => "dialog-information",
    };
}
