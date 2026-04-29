using Avalonia.Controls;
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
    private TrayIcon? _trayIcon;
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

    public event EventHandler? OpenRequested;

    public event EventHandler? QuitRequested;

    public event EventHandler? TrayUnavailable;

    public async Task StartAsync(AvaloniaApplication application, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(application);

        IsTrayAvailable = await ProbeSniWatcherAsync(cancellationToken).ConfigureAwait(false);
        if (!IsTrayAvailable)
        {
            _logger.LogInformation(
                "No StatusNotifierWatcher on the session bus — running in window-only mode (GNOME without AppIndicator extension is the typical case).");
            TrayUnavailable?.Invoke(this, EventArgs.Empty);
            return;
        }

        var menu = new NativeMenu
        {
            Items =
            {
                new NativeMenuItem("Open") { Command = new RelayCommand(() => OpenRequested?.Invoke(this, EventArgs.Empty)) },
                new NativeMenuItemSeparator(),
                new NativeMenuItem("Quit") { Command = new RelayCommand(() => QuitRequested?.Invoke(this, EventArgs.Empty)) },
            },
        };

        _trayIcon = new TrayIcon
        {
            ToolTipText = "Immich Folder Watch",
            Menu = menu,
            IsVisible = true,
        };
        _trayIcon.Clicked += (_, _) => OpenRequested?.Invoke(this, EventArgs.Empty);

        TrayIcon.SetIcons(application, new TrayIcons { _trayIcon });
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
                    "SNI watcher probe timed out after 3s — assuming no tray host (typical on bare GNOME).");
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
        _trayIcon?.Dispose();
        _trayIcon = null;
    }

    private sealed class RelayCommand : System.Windows.Input.ICommand
    {
        private readonly Action _action;

        public RelayCommand(Action action)
        {
            _action = action;
        }

        public event EventHandler? CanExecuteChanged
        {
            add { }
            remove { }
        }

        public bool CanExecute(object? parameter) => true;

        public void Execute(object? parameter) => _action();
    }
}
