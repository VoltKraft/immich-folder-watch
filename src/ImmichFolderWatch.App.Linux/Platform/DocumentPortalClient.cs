using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

/// <summary>
/// Resolves display-only host paths without replacing the granted FUSE access path.
/// Uses the document host-path attribute or Documents.GetHostPaths (interface v5).
/// Documents.Info cannot be called by sandboxed applications.
/// </summary>
public sealed class DocumentPortalClient
{
    private static readonly Regex DocMountPattern = new(
        @"^/run/user/\d+/doc/(?<token>[^/]+)(?<suffix>/.*)?$", RegexOptions.Compiled);
    private readonly DBusSession _session;
    private readonly ILogger<DocumentPortalClient> _logger;
    private readonly Func<string, string?> _readHostPathAttribute;
    internal TimeSpan ResponseTimeout { get; init; } = TimeSpan.FromSeconds(3);

    public DocumentPortalClient(DBusSession session)
        : this(session, NullLogger<DocumentPortalClient>.Instance) { }

    public DocumentPortalClient(DBusSession session, ILogger<DocumentPortalClient> logger)
        : this(session, logger, ReadHostPathAttribute) { }

    internal DocumentPortalClient(DBusSession session, ILogger<DocumentPortalClient> logger,
        Func<string, string?> readHostPathAttribute)
    {
        _session = session;
        _logger = logger;
        _readHostPathAttribute = readHostPathAttribute;
    }

    /// <summary>
    /// Returns a host path for a granted document mount, or null when unavailable.
    /// The result is only for display: filesystem operations must keep using the
    /// original mount path. Cancellation propagates; unavailable/older portals
    /// and timeouts return null so the caller can retain the access path as fallback.
    /// </summary>
    public async Task<string?> ResolveHostPathAsync(string mountPath, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrEmpty(mountPath)) return null;
        var match = DocMountPattern.Match(mountPath);
        if (!match.Success || match.Groups["token"].Value is "." or ".." or "by-app") return null;

        using var timeout = new CancellationTokenSource(ResponseTimeout);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        try
        {
            // FUSE metadata access can block; keep it off the UI thread. This
            // attribute also resolves nested paths and renamed exported folders.
            var attributeTask = Task.Run(() => _readHostPathAttribute(mountPath), linked.Token);
            ObserveLateFailure(attributeTask);
            var attributePath = await attributeTask.WaitAsync(linked.Token).ConfigureAwait(false);
            if (IsHostPath(attributePath)) return attributePath;

            var connection = await _session.GetAsync(linked.Token).ConfigureAwait(false);
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(destination: "org.freedesktop.portal.Documents",
                path: "/org/freedesktop/portal/documents", @interface: "org.freedesktop.portal.Documents",
                member: "GetHostPaths", signature: "as");
            var token = match.Groups["token"].Value;
            writer.WriteArray(new[] { token });
            var request = connection.CallMethodAsync(writer.CreateMessage(), ReadHostPathsReply, token);
            ObserveLateFailure(request);
            var documentPath = await request.WaitAsync(linked.Token).ConfigureAwait(false);
            return MapDocumentPath(documentPath, match.Groups["suffix"].Value);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException) when (timeout.IsCancellationRequested)
        {
            _logger.LogDebug("Document host-path lookup timed out; keeping the granted access path for display.");
            return null;
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Document host-path lookup unavailable; keeping the granted access path for display.");
            return null;
        }
    }

    internal static string? MapDocumentPath(string? documentPath, string mountSuffix)
    {
        if (!IsHostPath(documentPath)) return null;
        var parts = mountSuffix.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Any(part => part is "." or "..")) return null;
        if (parts.Length == 0) return documentPath;

        // A document mount exposes its original basename directly below the ID.
        // Append only the path inside that exported file/directory, not its name twice.
        var hostRoot = documentPath!.TrimEnd('/');
        var name = Path.GetFileName(hostRoot);
        if (!string.Equals(parts[0], name, StringComparison.Ordinal)) return null;
        return parts.Length == 1 ? documentPath : hostRoot + "/" + string.Join('/', parts.Skip(1));
    }

    private static string? ReadHostPathsReply(Message message, object? state)
    {
        var reader = message.GetBodyReader();
        var entries = reader.ReadArrayStart(DBusType.Struct);
        string? result = null;
        while (reader.HasNext(entries))
        {
            reader.AlignStruct();
            var token = reader.ReadString();
            var bytes = reader.ReadArrayOfByte();
            if (token == (string)state!) result = DecodePath(bytes);
        }
        return result;
    }

    private static string? DecodePath(byte[] bytes)
    {
        var nul = Array.IndexOf(bytes, (byte)0);
        var value = Encoding.UTF8.GetString(bytes, 0, nul < 0 ? bytes.Length : nul);
        return IsHostPath(value) ? value : null;
    }

    private static bool IsHostPath(string? value) =>
        !string.IsNullOrEmpty(value) && value[0] == '/' && !value.Contains('\0');

    private static string? ReadHostPathAttribute(string path)
    {
        if (!OperatingSystem.IsLinux()) return null;
        var buffer = new byte[4096];
        var length = GetXattr(path, "user.document-portal.host-path", buffer, (nuint)buffer.Length);
        return length > 0 && length <= buffer.Length ? DecodePath(buffer[..(int)length]) : null;
    }

    private static void ObserveLateFailure(Task task) =>
        _ = task.ContinueWith(static completed => _ = completed.Exception, CancellationToken.None,
            TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);

    [DllImport("libc", EntryPoint = "getxattr", SetLastError = true)]
    private static extern nint GetXattr([MarshalAs(UnmanagedType.LPUTF8Str)] string path,
        [MarshalAs(UnmanagedType.LPUTF8Str)] string name, [Out] byte[] value, nuint size);
}
