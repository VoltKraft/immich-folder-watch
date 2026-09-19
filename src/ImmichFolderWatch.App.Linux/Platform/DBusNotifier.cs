using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

/// <summary>Sends desktop notifications through the sandbox-accessible Notification portal.</summary>
public sealed class DBusNotifier : INotifier
{
    private const string ServiceName = "org.freedesktop.portal.Desktop";
    private const string ObjectPath = "/org/freedesktop/portal/desktop";
    private const string InterfaceName = "org.freedesktop.portal.Notification";

    private readonly DBusSession _session;
    private readonly ILogger<DBusNotifier> _logger;
    internal TimeSpan ResponseTimeout { get; init; } = TimeSpan.FromSeconds(3);

    public DBusNotifier(DBusSession session)
        : this(session, NullLogger<DBusNotifier>.Instance)
    {
    }

    public DBusNotifier(DBusSession session, ILogger<DBusNotifier> logger)
    {
        _session = session;
        _logger = logger;
    }

    /// <summary>
    /// Submits an independent notification using portal version 1 fields. Portal errors
    /// and timeouts are logged without interrupting synchronization. Cancellation
    /// propagates but cannot retract a notification the portal has already accepted.
    /// A successful submission does not guarantee the desktop displayed the notification.
    /// </summary>
    public async Task ShowAsync(
        string title,
        string body,
        NotificationKind kind = NotificationKind.Info,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        using var timeout = new CancellationTokenSource(ResponseTimeout);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        try
        {
            var connection = await _session.GetAsync(linked.Token).ConfigureAwait(false);
            linked.Token.ThrowIfCancellationRequested();
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(
                destination: ServiceName,
                path: ObjectPath,
                @interface: InterfaceName,
                member: "AddNotification",
                signature: "sa{sv}",
                flags: MessageFlags.None);
            // Reusing an ID replaces the previous notification; each event should remain independent.
            writer.WriteString(Guid.NewGuid().ToString("N"));
            writer.WriteDictionary(new Dictionary<string, VariantValue>
            {
                ["title"] = VariantValue.String(title),
                ["body"] = VariantValue.String(body),
                ["priority"] = VariantValue.String(MapPriority(kind)),
            });
            var request = connection.CallMethodAsync(writer.CreateMessage());
            // The shared D-Bus connection does not support cancelling an individual request.
            _ = request.ContinueWith(static completed => _ = completed.Exception, CancellationToken.None,
                TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
            await request.WaitAsync(linked.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException) when (timeout.IsCancellationRequested)
        {
            _logger.LogWarning("Notification portal request timed out: {Title}", title);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to deliver notification: {Title}", title);
        }
    }

    private static string MapPriority(NotificationKind kind) => kind switch
    {
        NotificationKind.Error => "urgent",
        NotificationKind.Warning => "high",
        _ => "normal",
    };
}
