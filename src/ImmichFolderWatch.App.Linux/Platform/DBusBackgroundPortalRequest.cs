using Microsoft.Extensions.Logging;
using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

/// <summary>Completes Background portal requests only after their asynchronous response.</summary>
public sealed class DBusBackgroundPortalRequest(DBusSession session, ILogger<DBusBackgroundPortalRequest> logger)
    : IBackgroundPortalRequest
{
    private const string Service = "org.freedesktop.portal.Desktop";
    private const string PortalPath = "/org/freedesktop/portal/desktop";
    private const string RequestInterface = "org.freedesktop.portal.Request";
    internal TimeSpan ResponseTimeout { get; init; } = TimeSpan.FromMinutes(2);

    public async Task<BackgroundPortalResponse> RequestAsync(bool autostart, CancellationToken cancellationToken = default)
    {
        using var timeout = new CancellationTokenSource(ResponseTimeout);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        try
        {
            return await RequestCoreAsync(autostart, linked.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (timeout.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
        {
            throw new TimeoutException("The Background portal did not respond before the request timed out.");
        }
    }

    private async Task<BackgroundPortalResponse> RequestCoreAsync(bool autostart, CancellationToken cancellationToken)
    {
        var connection = await session.GetAsync(cancellationToken).WaitAsync(cancellationToken).ConfigureAwait(false);
        var token = "ifw_background_" + Guid.NewGuid().ToString("N");
        var expectedPath = $"{PortalPath}/request/{connection.UniqueName!.TrimStart(':').Replace('.', '_')}/{token}";
        string? returnedPath = null;
        var response = new TaskCompletionSource<BackgroundPortalResponse>(TaskCreationOptions.RunContinuationsAsynchronously);
        var earlyResponses = new Dictionary<string, BackgroundPortalResponse>();
        var gate = new object();

        // Subscribe before invoking the method, including older portals that return a
        // different handle. Filter paths locally: Tmds 0.92.0 serializes PathNamespace
        // as an invalid D-Bus key; move this filter into the rule once that is fixed.
        var subscriptionTask = connection.AddMatchAsync(
            new MatchRule
            {
                Type = MessageType.Signal,
                Sender = Service,
                Interface = RequestInterface,
                Member = "Response",
            },
            static (message, _) => ReadResponse(message),
            (exception, signal, _, _) =>
            {
                if (exception is not null)
                {
                    response.TrySetException(exception);
                    return;
                }
                if (!signal.Path.StartsWith(PortalPath + "/request/", StringComparison.Ordinal))
                {
                    return;
                }

                lock (gate)
                {
                    if (returnedPath is null)
                    {
                        earlyResponses[signal.Path] = signal.Response;
                    }
                    else if (signal.Path == returnedPath)
                    {
                        response.TrySetResult(signal.Response);
                    }
                }
            },
            flags: ObserverFlags.None, emitOnCapturedContext: false).AsTask();
        IDisposable subscription;
        try
        {
            subscription = await subscriptionTask.WaitAsync(cancellationToken).ConfigureAwait(false);
        }
        catch
        {
            _ = DisposeLateSubscriptionAsync(subscriptionTask);
            throw;
        }
        using var subscriptionLifetime = subscription;

        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(
                destination: Service, path: PortalPath,
                @interface: "org.freedesktop.portal.Background", member: "RequestBackground", signature: "sa{sv}");
            writer.WriteString(string.Empty);
            writer.WriteDictionary(new Dictionary<string, VariantValue>
            {
                ["handle_token"] = VariantValue.String(token),
                ["autostart"] = VariantValue.Bool(autostart),
                ["commandline"] = VariantValue.Array(new[] { "immich-folder-watch", "--background" }),
                ["reason"] = VariantValue.String("Watch folders and upload media to Immich"),
            });
            var path = await connection.CallMethodAsync(writer.CreateMessage(),
                static (message, _) => message.GetBodyReader().ReadObjectPathAsString(), null)
                .WaitAsync(cancellationToken).ConfigureAwait(false);
            lock (gate)
            {
                returnedPath = path;
                if (earlyResponses.TryGetValue(path, out var earlyResponse))
                {
                    response.TrySetResult(earlyResponse);
                }
                earlyResponses.Clear();
            }

            return await response.Task.WaitAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            await CloseRequestAsync(connection, returnedPath ?? expectedPath).ConfigureAwait(false);
            throw;
        }
    }

    private async Task DisposeLateSubscriptionAsync(Task<IDisposable> subscriptionTask)
    {
        try
        {
            (await subscriptionTask.ConfigureAwait(false)).Dispose();
        }
        catch (Exception ex)
        {
            logger.LogDebug(ex, "The cancelled Background portal subscription did not complete.");
        }
    }

    private async Task CloseRequestAsync(DBusConnection connection, string path)
    {
        try
        {
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(destination: Service, path: path,
                @interface: RequestInterface, member: "Close");
            await connection.CallMethodAsync(writer.CreateMessage()).WaitAsync(TimeSpan.FromSeconds(3)).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            logger.LogDebug(ex, "Could not close the cancelled Background portal request.");
        }
    }

    private static (string Path, BackgroundPortalResponse Response) ReadResponse(Message message)
    {
        var reader = message.GetBodyReader();
        var code = reader.ReadUInt32();
        var results = reader.ReadDictionaryOfStringToVariantValue();
        return (message.PathAsString!, new BackgroundPortalResponse(code,
            results.TryGetValue("background", out var background) && background.GetBool(),
            results.TryGetValue("autostart", out var autostart) && autostart.GetBool()));
    }
}
