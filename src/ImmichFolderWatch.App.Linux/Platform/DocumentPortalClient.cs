using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

/// <summary>
/// Translates xdg-document-portal FUSE mount paths
/// (<c>/run/user/$UID/doc/&lt;token&gt;/...</c>) back to the original host
/// path the token was issued against, by calling
/// <c>org.freedesktop.portal.Documents.Info(token) → ay path, a{sa{u}} apps</c>.
/// The Flatpak manifest already grants
/// <c>--talk-name=org.freedesktop.portal.Documents</c>, so this works
/// out of the box inside the sandbox.
/// </summary>
public sealed class DocumentPortalClient
{
    private const string Service = "org.freedesktop.portal.Documents";
    private const string ObjectPath = "/org/freedesktop/portal/documents";
    private const string InterfaceName = "org.freedesktop.portal.Documents";

    private static readonly Regex DocMountPattern =
        new(@"^/run/user/\d+/doc/(?<token>[0-9a-fA-F]+)(/.*)?$", RegexOptions.Compiled);

    private readonly DBusSession _session;
    private readonly ILogger<DocumentPortalClient> _logger;

    public DocumentPortalClient(DBusSession session)
        : this(session, NullLogger<DocumentPortalClient>.Instance)
    {
    }

    public DocumentPortalClient(DBusSession session, ILogger<DocumentPortalClient> logger)
    {
        _session = session;
        _logger = logger;
    }

    /// <summary>
    /// Returns the host path if <paramref name="mountPath"/> looks like a
    /// doc-portal FUSE mount path AND the portal call succeeds. Returns
    /// null in every other case (manual paths, malformed input, portal
    /// errors, timeouts) — the caller should fall back to displaying
    /// the mount path verbatim.
    /// </summary>
    public async Task<string?> ResolveHostPathAsync(string mountPath, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrEmpty(mountPath))
        {
            return null;
        }

        var match = DocMountPattern.Match(mountPath);
        if (!match.Success)
        {
            return null;
        }

        var token = match.Groups["token"].Value;

        try
        {
            var connection = await _session.GetAsync(cancellationToken).ConfigureAwait(false);
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(
                destination: Service,
                path: ObjectPath,
                @interface: InterfaceName,
                member: "Info",
                signature: "s",
                flags: MessageFlags.None);
            writer.WriteString(token);
            var message = writer.CreateMessage();

            // The Documents portal proxy occasionally stalls under load;
            // cap the wait so the caller never blocks the UI thread.
            var infoTask = connection.CallMethodAsync(message, ReadInfoReply, this);
            var winner = await Task.WhenAny(
                infoTask,
                Task.Delay(TimeSpan.FromSeconds(3), cancellationToken)).ConfigureAwait(false);
            if (winner != infoTask)
            {
                _logger.LogInformation(
                    "Documents.Info({Token}) timed out after 3s — using mount path verbatim.",
                    token);
                return null;
            }

            return await infoTask.ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Documents.Info({Token}) failed; using mount path verbatim.", token);
            return null;
        }
    }

    private static string? ReadInfoReply(Message message, object? state)
    {
        var reader = message.GetBodyReader();
        var pathBytes = reader.ReadArrayOfByte();
        if (pathBytes.Length == 0)
        {
            return null;
        }

        // The portal returns a NUL-terminated UTF-8 byte string (`ay`).
        var nulIndex = Array.IndexOf<byte>(pathBytes, 0);
        var effectiveLength = nulIndex < 0 ? pathBytes.Length : nulIndex;
        if (effectiveLength == 0)
        {
            return null;
        }

        return Encoding.UTF8.GetString(pathBytes, 0, effectiveLength);
    }
}
