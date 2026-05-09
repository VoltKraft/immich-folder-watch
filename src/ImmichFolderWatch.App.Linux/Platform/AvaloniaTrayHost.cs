using Avalonia.Controls;
using Avalonia.Platform;
using Avalonia.Threading;
using ImmichFolderWatch.App.Shared.Resources;
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
    private const string IconAssetUri = "avares://immich-folder-watch/Assets/header-logo.png";

    private readonly DBusSession _session;
    private readonly ILogger<AvaloniaTrayHost> _logger;
    private TrayIcon? _trayIcon;
    private DispatcherUnhandledExceptionEventHandler? _dispatcherFilter;
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
    /// hidden window and no tray icon to bring it back.
    /// </summary>
    public bool IsTrayIconRegistered { get; private set; }

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

        // SNI watcher present (KDE Plasma, GNOME with AppIndicator
        // extension, etc.) — register the TrayIcon. Wrap the whole
        // construction in try/catch so a half-broken AppIndicator
        // implementation that surfaces as ServiceUnknown / Wayland
        // protocol fault degrades to the existing tray-less banner
        // instead of taking the GUI down with it.
        try
        {
            await Dispatcher.UIThread.InvokeAsync(() => RegisterTrayIcon(application));
            _logger.LogInformation(
                "Tray icon registered via StatusNotifierWatcher.");
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex,
                "Tray icon registration failed despite SNI watcher detection — falling back to window-only mode.");
            IsTrayIconRegistered = false;
            _trayIcon = null;
            TrayUnavailable?.Invoke(this, EventArgs.Empty);
        }
    }

    private void RegisterTrayIcon(AvaloniaApplication application)
    {
        WindowIcon icon;
        using (var iconStream = AssetLoader.Open(new Uri(IconAssetUri)))
        {
            icon = new WindowIcon(iconStream);
        }

        var menu = new NativeMenu();

        var openItem = new NativeMenuItem(Strings.Tray_Open);
        openItem.Click += (_, _) => OpenRequested?.Invoke(this, EventArgs.Empty);
        menu.Items.Add(openItem);

        menu.Items.Add(new NativeMenuItemSeparator());

        var quitItem = new NativeMenuItem(Strings.Tray_Quit);
        quitItem.Click += (_, _) => QuitRequested?.Invoke(this, EventArgs.Empty);
        menu.Items.Add(quitItem);

        var trayIcon = new TrayIcon
        {
            Icon = icon,
            ToolTipText = "Immich Folder Watch",
            Menu = menu,
            IsVisible = true,
        };
        trayIcon.Clicked += (_, _) => OpenRequested?.Invoke(this, EventArgs.Empty);

        // Avalonia 11.3.x's DBusTrayIconImpl.CreateTrayIcon does the
        // actual SNI registration on a continuation off SetIcons; on
        // GNOME-with-AppIndicator setups where the watcher claims the
        // name but the AppIndicator backend is half-broken, that
        // continuation surfaces ServiceUnknown via Task.ThrowAsync —
        // bypassing the synchronous try/catch around SetIcons AND the
        // TaskScheduler.UnobservedTaskException net in App.axaml.cs
        // (because ThrowAsync is "explicitly rethrown", not orphaned).
        // Catch that specific class of failure on the dispatcher so the
        // GUI degrades to window-only mode instead of dying.
        InstallDispatcherFilter();

        var trayIcons = new TrayIcons { trayIcon };
        TrayIcon.SetIcons(application, trayIcons);

        _trayIcon = trayIcon;
        IsTrayIconRegistered = true;
    }

    private void InstallDispatcherFilter()
    {
        if (_dispatcherFilter is not null)
        {
            return;
        }

        _dispatcherFilter = (sender, args) =>
        {
            var stack = args.Exception.ToString();
            if (!stack.Contains("Avalonia.FreeDesktop", StringComparison.Ordinal)
                && !stack.Contains("DBusTrayIcon", StringComparison.Ordinal))
            {
                return;
            }

            args.Handled = true;
            _logger.LogWarning(args.Exception,
                "Avalonia tray-icon background registration faulted (likely AppIndicator/SNI implementation mismatch); falling back to window-only mode.");

            IsTrayIconRegistered = false;
            var icon = _trayIcon;
            _trayIcon = null;
            if (icon is not null)
            {
                try
                {
                    icon.IsVisible = false;
                    icon.Dispose();
                }
                catch (Exception ex)
                {
                    _logger.LogDebug(ex, "Tray icon dispose failed during fallback; ignoring.");
                }
            }

            UninstallDispatcherFilter();
            TrayUnavailable?.Invoke(this, EventArgs.Empty);
        };

        Dispatcher.UIThread.UnhandledException += _dispatcherFilter;
    }

    private void UninstallDispatcherFilter()
    {
        if (_dispatcherFilter is null)
        {
            return;
        }

        Dispatcher.UIThread.UnhandledException -= _dispatcherFilter;
        _dispatcherFilter = null;
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
        UninstallDispatcherFilter();

        if (_trayIcon is null)
        {
            return;
        }

        try
        {
            _trayIcon.IsVisible = false;
            _trayIcon.Dispose();
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Tray icon dispose failed; ignoring during shutdown.");
        }

        _trayIcon = null;
    }
}
