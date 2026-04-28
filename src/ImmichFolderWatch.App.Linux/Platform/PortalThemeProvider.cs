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

    public void Initialize() => _ = RefreshAsync();

    public void Refresh() => _ = RefreshAsync();

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
    {
        var reader = message.GetBodyReader();
        var variant = reader.ReadVariantValue();
        return variant.GetUInt32();
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
    }
}
