using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using SocketIOClient.Protocol.Http;
using SocketIOClient.Protocol.WebSocket;
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
    private ConnectionLifetime? _connectionLifetime;

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

        var transportError = AppConfigValidator.ValidateServerApiUrl(_config.Immich.ServerApiUrl, _config.Immich.AllowInsecureHttp);
        if (transportError is not null)
        {
            throw new InvalidOperationException(transportError);
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
            ReconnectionDelayMax = 30000,
            ConnectionTimeout = TimeSpan.FromSeconds(10),
            ExtraHeaders = new Dictionary<string, string>
            {
                ["x-api-key"] = _config.Immich.ApiKey ?? string.Empty,
            },
        };

        var lifetime = new ConnectionLifetime(cancellationToken);
        var socket = new SocketIOClient.SocketIO(socketUri, options, services =>
        {
            // Each reconnect/upgrade scope owns fresh hardened transports. SocketIO 4
            // disposes its scopes, but not its root provider, so avoid singleton clients.
            services.RemoveAll<IHttpClient>();
            services.RemoveAll<IWebSocketClient>();
            services.AddScoped<IHttpClient>(_ =>
            {
                lifetime.ThrowIfStopping();
                return new ImmichRealtimeHttpClient(socketUri, lifetime.Token);
            });
            services.AddScoped<IWebSocketClient>(_ =>
            {
                lifetime.ThrowIfStopping();
                return new ImmichRealtimeWebSocket(socketUri, lifetime.Token);
            });
        });

        foreach (var eventName in SubscribedEvents)
        {
            var localEvent = eventName;
            socket.On(localEvent, _ =>
            {
                _logger.LogDebug("Realtime event received: {Event}", localEvent);
                RaiseRemoteChangeDetected();
                return Task.CompletedTask;
            });
        }

        socket.OnConnected += (_, _) => _logger.LogInformation("Realtime connection to Immich established at {Uri}.", socketUri);
        socket.OnDisconnected += (_, reason) => _logger.LogInformation("Realtime connection disconnected: {Reason}", reason);
        socket.OnError += (_, err) => _logger.LogWarning("Realtime connection error: {Error}", err);
        socket.OnReconnectAttempt += (_, attempt) => _logger.LogDebug("Realtime reconnect attempt #{Attempt}.", attempt);
        socket.OnReconnectError += (_, _) => _logger.LogWarning("Realtime reconnect failed; will continue retrying.");

        _socket = socket;
        _connectionLifetime = lifetime;

        try
        {
            await socket.ConnectAsync(cancellationToken);
        }
        catch (Exception ex)
        {
            lifetime.Dispose();
            socket.Dispose();
            if (ReferenceEquals(_socket, socket))
            {
                _socket = null;
                _connectionLifetime = null;
            }
            _logger.LogWarning(ex, "Realtime connection attempt failed; sync will rely on periodic polling.");
        }
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        if (_socket is null)
        {
            return;
        }

        var socket = _socket;
        var lifetime = _connectionLifetime;
        // Gate reconnect factories before graceful shutdown. Upstream 4.0.5 can
        // otherwise create another session after Dispose releases the current one.
        lifetime?.StopCreatingTransports();
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(2));
            await socket.DisconnectAsync(timeout.Token);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Realtime disconnect threw during stop.");
        }

        finally
        {
            lifetime?.Dispose();
            socket.Dispose();
            _socket = null;
            _connectionLifetime = null;
        }
    }

    private sealed class ConnectionLifetime : IDisposable
    {
        private readonly CancellationTokenSource _source;
        private int _stopping;
        private int _disposed;

        public ConnectionLifetime(CancellationToken cancellationToken)
        {
            _source = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            Token = _source.Token;
        }

        public CancellationToken Token { get; }
        public void StopCreatingTransports() => Interlocked.Exchange(ref _stopping, 1);

        public void ThrowIfStopping()
        {
            if (Volatile.Read(ref _stopping) != 0) throw new OperationCanceledException(Token);
            Token.ThrowIfCancellationRequested();
        }

        public void Dispose()
        {
            StopCreatingTransports();
            if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
            _source.Cancel();
            _source.Dispose();
        }
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
