using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;
using AvaloniaApplication = Avalonia.Application;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class AvaloniaTrayHost : IDisposable
{
    private const string DBusService = "org.freedesktop.DBus";
    private const string DBusPath = "/org/freedesktop/DBus";
    private const string DBusInterface = "org.freedesktop.DBus";
    private const string SniWatcherName = "org.kde.StatusNotifierWatcher";

    private readonly DBusSession _session;
    private readonly ILogger<AvaloniaTrayHost> _logger;
    private bool _disposed;

    public AvaloniaTrayHost(DBusSession session)
        : this(session, NullLogger<AvaloniaTrayHost>.Instance)
    {
    }

    public AvaloniaTrayHost(DBusSession session, ILogger<AvaloniaTrayHost> logger)
    {
        _session = session;
        _logger = logger;
    }

    public bool IsTrayAvailable { get; private set; }

    /// <summary>
    /// True only after a TrayIcon has actually been registered and is
    /// expected to be visible to the user. The MainWindow predicates
    /// "close = hide" on this so the user is never stranded with a
    /// hidden window and no tray icon to bring it back. 3.8.D sets
    /// this true when the SNI registration succeeds; 3.8.C ships it
    /// as always-false so close keeps exiting until the tray is real.
    /// </summary>
    public bool IsTrayIconRegistered { get; private set; }

    // OpenRequested + QuitRequested are reserved for the Phase 6 tray
    // re-activation; suppress the "never invoked" warning until then.
#pragma warning disable CS0067
    public event EventHandler? OpenRequested;

    public event EventHandler? QuitRequested;
#pragma warning restore CS0067

    public event EventHandler? TrayUnavailable;

    public async Task StartAsync(AvaloniaApplication application, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(application);

        // Phase 4 ships the tray-less default per Plan §4 / Decision #3.
        // Avalonia 11.3.x's TrayIcon registration crashes the process with
        // org.freedesktop.DBus.Error.ServiceUnknown on bare-GNOME / Flatpak
        // setups where the SNI watcher claims to exist but the actual
        // registration fails downstream. The probe below is purely
        // informational so the QA log shows whether SNI was detected;
        // the icon itself stays unregistered until Phase 6 QA on KDE
        // Plasma can validate the proper registration path with full
        // error handling around it.
        IsTrayAvailable = await ProbeSniWatcherAsync(cancellationToken).ConfigureAwait(false);
        if (IsTrayAvailable)
        {
            _logger.LogInformation(
                "StatusNotifierWatcher detected on the session bus — tray icon registration is intentionally deferred to Phase 6 QA. Running in window-only mode for now.");
        }
        else
        {
            _logger.LogInformation(
                "No StatusNotifierWatcher on the session bus — running in window-only mode (GNOME without AppIndicator extension is the typical case).");
        }

        TrayUnavailable?.Invoke(this, EventArgs.Empty);
    }

    private async Task<bool> ProbeSniWatcherAsync(CancellationToken cancellationToken)
    {
        try
        {
            var connection = await _session.GetAsync(cancellationToken).ConfigureAwait(false);
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(
                destination: DBusService,
                path: DBusPath,
                @interface: DBusInterface,
                member: "NameHasOwner",
                signature: "s",
                flags: MessageFlags.None);
            writer.WriteString(SniWatcherName);
            var message = writer.CreateMessage();

            // The Flatpak D-Bus proxy can stall on filtered NameHasOwner
            // queries instead of returning AccessDenied; cap the wait so
            // the tray UI never sits on "pending probe" indefinitely.
            var probeTask = connection.CallMethodAsync(message, ReadBoolReply, this);
            var winner = await Task.WhenAny(probeTask, Task.Delay(TimeSpan.FromSeconds(3), cancellationToken))
                .ConfigureAwait(false);
            if (winner != probeTask)
            {
                _logger.LogInformation(
                    "SNI watcher probe timed out after 3s — assuming no tray host.");
                return false;
            }

            return await probeTask.ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "SNI watcher probe failed; defaulting to window-only mode");
            return false;
        }
    }

    private static bool ReadBoolReply(Message message, object? state)
    {
        var reader = message.GetBodyReader();
        return reader.ReadBool();
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
    }
}
