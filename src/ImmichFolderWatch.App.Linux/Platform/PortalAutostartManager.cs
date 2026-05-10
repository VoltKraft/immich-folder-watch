using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class PortalAutostartManager : IAutoStartManager
{
    private const string PortalService = "org.freedesktop.portal.Desktop";
    private const string PortalPath = "/org/freedesktop/portal/desktop";
    private const string BackgroundIface = "org.freedesktop.portal.Background";
    private const string AutostartFlagFileName = "autostart-requested";

    private readonly DBusSession _session;
    private readonly IPlatformPaths _paths;
    private readonly ILogger<PortalAutostartManager> _logger;

    public PortalAutostartManager(DBusSession session, IPlatformPaths paths)
        : this(session, paths, NullLogger<PortalAutostartManager>.Instance)
    {
    }

    public PortalAutostartManager(DBusSession session, IPlatformPaths paths, ILogger<PortalAutostartManager> logger)
    {
        _session = session;
        _paths = paths;
        _logger = logger;
    }

    public Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default)
        => Task.FromResult(File.Exists(GetFlagPath()));

    public async Task EnableAsync(CancellationToken cancellationToken = default)
    {
        await CallRequestBackgroundAsync(autostart: true, cancellationToken).ConfigureAwait(false);
        try
        {
            Directory.CreateDirectory(_paths.GetUserDataRoot());
            await File.WriteAllTextAsync(GetFlagPath(), DateTime.UtcNow.ToString("O"), cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to persist autostart flag");
        }
    }

    public async Task DisableAsync(CancellationToken cancellationToken = default)
    {
        await CallRequestBackgroundAsync(autostart: false, cancellationToken).ConfigureAwait(false);
        try
        {
            var path = GetFlagPath();
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to clear autostart flag");
        }
    }

    private string GetFlagPath() => Path.Combine(_paths.GetUserDataRoot(), AutostartFlagFileName);

    private async Task CallRequestBackgroundAsync(bool autostart, CancellationToken cancellationToken)
    {
        try
        {
            var connection = await _session.GetAsync(cancellationToken).ConfigureAwait(false);
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(
                destination: PortalService,
                path: PortalPath,
                @interface: BackgroundIface,
                member: "RequestBackground",
                signature: "sa{sv}",
                flags: MessageFlags.None);
            writer.WriteString(string.Empty);
            var options = new Dictionary<string, VariantValue>
            {
                ["autostart"] = VariantValue.Bool(autostart),
                ["background"] = VariantValue.Bool(true),
                ["commandline"] = VariantValue.Array(new[] { "immich-folder-watch", "--background" }),
                ["reason"] = VariantValue.String("Watch folders and upload media to Immich"),
            };
            writer.WriteDictionary(options);
            var message = writer.CreateMessage();
            await connection.CallMethodAsync(message).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "RequestBackground(autostart={Autostart}) failed", autostart);
            throw;
        }
    }
}
