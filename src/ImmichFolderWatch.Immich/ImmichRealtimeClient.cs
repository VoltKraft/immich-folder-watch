using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using Microsoft.Extensions.Logging;
using SocketIOClient;

namespace ImmichFolderWatch.Immich;

public sealed class ImmichRealtimeClient : IImmichRealtimeClient
{
    private static readonly string[] SubscribedEvents =
    {
        "on_upload_success",
        "on_asset_trash",
        "on_asset_delete",
        "on_asset_update",
        "on_asset_restore",
        "on_album_create",
        "on_album_update",
        "on_album_delete",
        "on_album_invite",
    };

    private readonly AppConfig _config;
    private readonly ILogger<ImmichRealtimeClient> _logger;
    private SocketIOClient.SocketIO? _socket;

    public ImmichRealtimeClient(AppConfig config, ILogger<ImmichRealtimeClient> logger)
    {
        _config = config;
        _logger = logger;
    }

    public event EventHandler? RemoteChangeDetected;

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        if (_socket is not null)
        {
            return;
        }

        if (!TryBuildSocketUri(_config.Immich.ServerApiUrl, out var socketUri))
        {
            _logger.LogWarning(
                "Realtime sync disabled: server URL '{Url}' could not be parsed.",
                _config.Immich.ServerApiUrl);
            return;
        }

        var options = new SocketIOOptions
        {
            Reconnection = true,
            ReconnectionAttempts = int.MaxValue,
            ReconnectionDelay = 2000,
            ReconnectionDelayMax = 30000,
            ConnectionTimeout = TimeSpan.FromSeconds(10),
            ExtraHeaders = new Dictionary<string, string>
            {
                ["x-api-key"] = _config.Immich.ApiKey ?? string.Empty,
            },
        };

        var socket = new SocketIOClient.SocketIO(socketUri, options);

        foreach (var eventName in SubscribedEvents)
        {
            var localEvent = eventName;
            socket.On(localEvent, _ =>
            {
                _logger.LogDebug("Realtime event received: {Event}", localEvent);
                RaiseRemoteChangeDetected();
            });
        }

        socket.OnConnected += (_, _) => _logger.LogInformation("Realtime connection to Immich established at {Uri}.", socketUri);
        socket.OnDisconnected += (_, reason) => _logger.LogInformation("Realtime connection disconnected: {Reason}", reason);
        socket.OnError += (_, err) => _logger.LogWarning("Realtime connection error: {Error}", err);
        socket.OnReconnectAttempt += (_, attempt) => _logger.LogDebug("Realtime reconnect attempt #{Attempt}.", attempt);
        socket.OnReconnectFailed += (_, _) => _logger.LogWarning("Realtime reconnect failed; will continue retrying.");

        _socket = socket;

        try
        {
            await socket.ConnectAsync(cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Realtime connection attempt failed; sync will rely on periodic polling until reconnected.");
        }
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        if (_socket is null)
        {
            return;
        }

        try
        {
            await _socket.DisconnectAsync();
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Realtime disconnect threw during stop.");
        }

        _socket.Dispose();
        _socket = null;
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync(CancellationToken.None);
    }

    private void RaiseRemoteChangeDetected()
    {
        try
        {
            RemoteChangeDetected?.Invoke(this, EventArgs.Empty);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Realtime event handler threw.");
        }
    }

    private static bool TryBuildSocketUri(string serverApiUrl, out Uri socketUri)
    {
        socketUri = null!;
        if (string.IsNullOrWhiteSpace(serverApiUrl))
        {
            return false;
        }

        if (!Uri.TryCreate(serverApiUrl, UriKind.Absolute, out var apiUri))
        {
            return false;
        }

        var pathSegments = apiUri.AbsolutePath
            .Split('/', StringSplitOptions.RemoveEmptyEntries)
            .ToList();

        if (pathSegments.Count > 0 && string.Equals(pathSegments[^1], "api", StringComparison.OrdinalIgnoreCase))
        {
            pathSegments.RemoveAt(pathSegments.Count - 1);
        }

        var rebuiltPath = pathSegments.Count == 0
            ? "/"
            : "/" + string.Join('/', pathSegments) + "/";

        var builder = new UriBuilder
        {
            Scheme = apiUri.Scheme,
            Host = apiUri.Host,
            Port = apiUri.IsDefaultPort ? -1 : apiUri.Port,
            Path = rebuiltPath,
        };

        socketUri = builder.Uri;
        return true;
    }
}
