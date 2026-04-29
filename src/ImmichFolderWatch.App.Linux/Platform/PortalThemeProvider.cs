using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class PortalThemeProvider : IThemeProvider
{
    private const string PortalService = "org.freedesktop.portal.Desktop";
    private const string PortalPath = "/org/freedesktop/portal/desktop";
    private const string SettingsIface = "org.freedesktop.portal.Settings";
    private const string AppearanceNamespace = "org.freedesktop.appearance";
    private const string ColorSchemeKey = "color-scheme";

    private readonly DBusSession _session;
    private readonly ILogger<PortalThemeProvider> _logger;
    private bool _isDark;
    private bool _disposed;
    private IDisposable? _signalSubscription;

    public PortalThemeProvider(DBusSession session)
        : this(session, NullLogger<PortalThemeProvider>.Instance)
    {
    }

    public PortalThemeProvider(DBusSession session, ILogger<PortalThemeProvider> logger)
    {
        _session = session;
        _logger = logger;
    }

    public bool IsDark => _isDark;

    public AccentColor Accent { get; } = new(0, 120, 215);

    public event EventHandler? ThemeChanged;

    public void Initialize() => _ = InitializeAsync();

    public void Refresh() => _ = RefreshAsync();

    private async Task InitializeAsync()
    {
        await RefreshAsync().ConfigureAwait(false);
        await SubscribeAsync().ConfigureAwait(false);
    }

    private async Task SubscribeAsync()
    {
        if (_signalSubscription is not null)
        {
            return;
        }

        try
        {
            var connection = await _session.GetAsync().ConfigureAwait(false);
            var subscription = await connection.WatchSignalAsync(
                PortalService,
                PortalPath,
                SettingsIface,
                "SettingChanged",
                (MessageValueReader<uint>)ReadSettingChangedSignal,
                (Action<Exception?, uint>)HandleSettingChanged,
                this,
                false,
                ObserverFlags.None).ConfigureAwait(false);
            _signalSubscription = subscription;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to subscribe to Settings portal SettingChanged signal");
        }
    }

    private static uint ReadSettingChangedSignal(Message message, object? state)
    {
        var reader = message.GetBodyReader();
        var ns = reader.ReadString();
        var key = reader.ReadString();
        if (!string.Equals(ns, AppearanceNamespace, StringComparison.Ordinal)
            || !string.Equals(key, ColorSchemeKey, StringComparison.Ordinal))
        {
            return uint.MaxValue;
        }

        return UnwrapNestedUInt32(reader.ReadVariantValue());
    }

    private void HandleSettingChanged(Exception? exception, uint scheme)
    {
        if (exception is not null || scheme == uint.MaxValue)
        {
            return;
        }

        ApplyColorScheme(scheme);
    }

    private async Task RefreshAsync()
    {
        try
        {
            var connection = await _session.GetAsync().ConfigureAwait(false);
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(
                destination: PortalService,
                path: PortalPath,
                @interface: SettingsIface,
                member: "Read",
                signature: "ss",
                flags: MessageFlags.None);
            writer.WriteString(AppearanceNamespace);
            writer.WriteString(ColorSchemeKey);
            var message = writer.CreateMessage();

            var scheme = await connection.CallMethodAsync(message, ReadColorSchemeReply, this).ConfigureAwait(false);
            ApplyColorScheme(scheme);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to read color-scheme from Settings portal");
        }
    }

    private static uint ReadColorSchemeReply(Message message, object? state)
        => UnwrapNestedUInt32(message.GetBodyReader().ReadVariantValue());

    private static uint UnwrapNestedUInt32(VariantValue variant)
    {
        // xdg-desktop-portal Settings.Read returns a `v` whose payload is
        // itself a variant on most backends (dconf, GSettings) — so the
        // outer ReadVariantValue gives us a Variant-typed VariantValue
        // that we have to unwrap once more before the actual UInt32.
        while (variant.Type == VariantValueType.Variant)
        {
            variant = variant.GetVariantValue();
        }

        return variant.Type == VariantValueType.UInt32
            ? variant.GetUInt32()
            : uint.MaxValue;
    }

    private void ApplyColorScheme(uint scheme)
    {
        var dark = scheme == 1;
        if (dark == _isDark)
        {
            return;
        }

        _isDark = dark;
        ThemeChanged?.Invoke(this, EventArgs.Empty);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _signalSubscription?.Dispose();
        _signalSubscription = null;
    }
}
