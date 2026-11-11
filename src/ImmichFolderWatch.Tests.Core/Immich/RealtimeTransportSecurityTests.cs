using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using ImmichFolderWatch.Immich;
using ImmichFolderWatch.Core.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using SocketIOClient.Protocol.Http;

namespace ImmichFolderWatch.Tests.Core.Immich;

public sealed class RealtimeTransportSecurityTests
{
    [Fact]
    public async Task WebSocket_RejectsOversizedFragmentedMessage()
    {
        using var server = new TcpListener(IPAddress.Loopback, 0);
        server.Start();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var sending = SendOversizedWebSocketMessageAsync(server, timeout.Token);
        using var socket = new ImmichRealtimeWebSocket(Address(server, "http"));
        await socket.ConnectAsync(Address(server, "ws"), timeout.Token);

        var error = await Assert.ThrowsAsync<WebSocketException>(async () =>
        {
            while (true) await socket.ReceiveAsync(new ArraySegment<byte>(new byte[16384]), timeout.Token);
        });

        Assert.Contains("byte limit", error.Message);
        await sending;
    }

    [Fact]
    public async Task Polling_DoesNotForwardApiKeyToRedirectTarget()
    {
        using var destination = new TcpListener(IPAddress.Loopback, 0);
        destination.Start();
        using var server = new TcpListener(IPAddress.Loopback, 0);
        server.Start();
        var origin = Address(server, "http");
        var response = ReplyOnceAsync(server, $"HTTP/1.1 302 Found\r\nLocation: {Address(destination, "http")}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
        using var client = new ImmichRealtimeHttpClient(origin);
        client.SetDefaultHeader("x-api-key", "synthetic-test-key");

        var request = new HttpRequest { Uri = origin };
        var error = await Assert.ThrowsAsync<HttpRequestException>(() => client.SendAsync(request, CancellationToken.None));

        Assert.Equal(HttpStatusCode.Found, error.StatusCode);
        Assert.Contains("x-api-key: synthetic-test-key", await response);
        Assert.False(destination.Pending());
    }

    [Fact]
    public async Task WebSocket_DoesNotForwardApiKeyToRedirectTarget()
    {
        using var destination = new TcpListener(IPAddress.Loopback, 0);
        destination.Start();
        using var server = new TcpListener(IPAddress.Loopback, 0);
        server.Start();
        var response = ReplyOnceAsync(server, $"HTTP/1.1 302 Found\r\nLocation: {Address(destination, "http")}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
        using var socket = new ImmichRealtimeWebSocket(Address(server, "http"));
        socket.SetDefaultHeader("x-api-key", "synthetic-test-key");
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));

        await Assert.ThrowsAsync<WebSocketException>(() => socket.ConnectAsync(Address(server, "ws"), timeout.Token));

        Assert.Contains("x-api-key: synthetic-test-key", await response);
        Assert.False(destination.Pending());
    }

    [Fact]
    public async Task Polling_RejectsOversizedResponseBeforeBufferingBody()
    {
        using var server = new TcpListener(IPAddress.Loopback, 0);
        server.Start();
        var response = ReplyOnceAsync(server, $"HTTP/1.1 200 OK\r\nContent-Length: {ImmichRealtimeHttpClient.MaximumMessageBytes + 1}\r\nConnection: close\r\n\r\n");
        using var client = new ImmichRealtimeHttpClient(Address(server, "http"));
        var request = new HttpRequest { Uri = Address(server, "http") };

        await Assert.ThrowsAsync<HttpRequestException>(() => client.SendAsync(request, CancellationToken.None));
        await response;
    }

    [Fact]
    public async Task Transports_RejectCrossOriginAndDowngradeRequestsBeforeConnecting()
    {
        using var client = new ImmichRealtimeHttpClient(new Uri("https://immich.example.test/"));
        var request = new HttpRequest { Uri = new Uri("http://immich.example.test/socket.io") };
        await Assert.ThrowsAsync<HttpRequestException>(() => client.SendAsync(request, CancellationToken.None));
        await Assert.ThrowsAsync<HttpRequestException>(() => client.SendAsync(new HttpRequest { Uri = new Uri("https://other.example.test/") }, CancellationToken.None));
        using var socket = new ImmichRealtimeWebSocket(new Uri("https://immich.example.test/"));
        await Assert.ThrowsAsync<HttpRequestException>(() => socket.ConnectAsync(new Uri("ws://immich.example.test/socket.io"), CancellationToken.None));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RealtimeClient_UpgradesPollingReceivesEventsAndStops(bool cancelInitialConnection)
    {
        using var server = new TcpListener(IPAddress.Loopback, 0);
        server.Start();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var config = new AppConfig
        {
            Immich = new ImmichSettings
            {
                ServerApiUrl = new Uri(Address(server, "http"), "api").ToString(),
                AllowInsecureHttp = true,
                ApiKey = "synthetic-test-key",
            },
        };
        await using var client = new ImmichRealtimeClient(config, NullLogger<ImmichRealtimeClient>.Instance);
        var changed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        client.RemoteChangeDetected += (_, _) => changed.TrySetResult();

        if (cancelInitialConnection)
        {
            using var canceledAttempt = CancellationTokenSource.CreateLinkedTokenSource(timeout.Token);
            var starting = client.StartAsync(canceledAttempt.Token);
            using var stalled = await server.AcceptTcpClientAsync(timeout.Token);
            canceledAttempt.Cancel();
            await starting.WaitAsync(timeout.Token);
        }

        var serving = ServeSocketIoUpgradeAsync(server, timeout.Token);
        await client.StartAsync(timeout.Token);
        await changed.Task.WaitAsync(timeout.Token);
        await client.StopAsync(timeout.Token);
        await serving;
    }

    [Fact]
    public async Task RealtimeClient_StopDuringReconnectPreventsLaterConnections()
    {
        using var server = new TcpListener(IPAddress.Loopback, 0);
        server.Start();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        var disconnect = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var serving = ServeSocketIoUpgradeAsync(server, timeout.Token, disconnect.Task);
        var config = new AppConfig
        {
            Immich = new ImmichSettings
            {
                ServerApiUrl = new Uri(Address(server, "http"), "api").ToString(),
                AllowInsecureHttp = true,
                ApiKey = "synthetic-test-key",
            },
        };
        await using var client = new ImmichRealtimeClient(config, NullLogger<ImmichRealtimeClient>.Instance);
        await client.StartAsync(timeout.Token);
        // Bound upstream's randomized retry delay for a deterministic lifecycle test.
        var field = typeof(ImmichRealtimeClient).GetField("_socket", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
        var socket = Assert.IsType<SocketIOClient.SocketIO>(field.GetValue(client));
        socket.Options.ReconnectionDelayMax = 1;
        socket.Options.ConnectionTimeout = TimeSpan.FromMilliseconds(100);
        disconnect.SetResult();
        await serving;
        using var stalledReconnect = await server.AcceptTcpClientAsync(timeout.Token);

        await client.StopAsync(timeout.Token);
        // Observe beyond the bounded attempt timeout: its failed handshake may
        // finish asynchronously after Stop has disposed that scope.
        using var observation = new CancellationTokenSource(TimeSpan.FromSeconds(1));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
        {
            using var unexpected = await server.AcceptTcpClientAsync(observation.Token);
        });
        Assert.False(socket.Connected);
    }

    private static async Task ServeSocketIoUpgradeAsync(TcpListener listener, CancellationToken cancellationToken, Task? forceDisconnect = null)
    {
        var pollingSeen = false;
        var namespaceConnectSeen = false;
        while (true)
        {
            using var connection = await listener.AcceptTcpClientAsync(cancellationToken);
            await using var stream = connection.GetStream();
            using var reader = new StreamReader(stream, Encoding.ASCII, leaveOpen: true);
            var requestLine = await reader.ReadLineAsync(cancellationToken);
            var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            while (await reader.ReadLineAsync(cancellationToken) is { Length: > 0 } line)
            {
                var parts = line.Split(':', 2);
                headers[parts[0]] = parts[1].Trim();
            }
            Assert.Equal("synthetic-test-key", headers["x-api-key"]);
            if (headers.TryGetValue("Sec-WebSocket-Key", out var key))
            {
                Assert.True(pollingSeen);
                Assert.True(namespaceConnectSeen);
                Assert.Contains("transport=websocket", requestLine);
                Assert.Contains("sid=synthetic-session", requestLine);
                // RFC 6455 handshake digest, not an authentication primitive.
                var accept = Convert.ToBase64String(SHA1.HashData(Encoding.ASCII.GetBytes(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")));
                await stream.WriteAsync(Encoding.ASCII.GetBytes($"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"), cancellationToken);
                using var socket = WebSocket.CreateFromStream(stream, true, null, Timeout.InfiniteTimeSpan);
                var buffer = new byte[1024];
                var upgrade = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), cancellationToken);
                Assert.Equal("5", Encoding.UTF8.GetString(buffer, 0, upgrade.Count));
                await socket.SendAsync(Encoding.UTF8.GetBytes("40{\"sid\":\"synthetic-namespace\"}"), WebSocketMessageType.Text, true, cancellationToken);
                await socket.SendAsync(Encoding.UTF8.GetBytes("42[\"on_asset_update\",{}]"), WebSocketMessageType.Text, true, cancellationToken);
                if (forceDisconnect is not null)
                {
                    await forceDisconnect.WaitAsync(cancellationToken);
                    socket.Abort();
                    return;
                }
                var disconnect = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), cancellationToken);
                Assert.Equal("41", Encoding.UTF8.GetString(buffer, 0, disconnect.Count));
                var close = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), cancellationToken);
                Assert.Equal(WebSocketMessageType.Close, close.MessageType);
                await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, string.Empty, cancellationToken);
                return;
            }

            string body;
            if (requestLine!.StartsWith("POST ", StringComparison.Ordinal))
            {
                var requestBody = new char[int.Parse(headers["Content-Length"])];
                Assert.Equal(requestBody.Length, await reader.ReadBlockAsync(requestBody.AsMemory(), cancellationToken));
                Assert.Equal("40", new string(requestBody));
                namespaceConnectSeen = true;
                body = "ok";
            }
            else
            {
                Assert.Contains("transport=polling", requestLine);
                pollingSeen = true;
                body = "0{\"sid\":\"synthetic-session\",\"upgrades\":[\"websocket\"],\"pingInterval\":25000,\"pingTimeout\":20000}";
            }
            await stream.WriteAsync(Encoding.ASCII.GetBytes($"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {Encoding.UTF8.GetByteCount(body)}\r\nConnection: close\r\n\r\n{body}"), cancellationToken);
        }
    }

    private static Uri Address(TcpListener listener, string scheme) =>
        new($"{scheme}://127.0.0.1:{((IPEndPoint)listener.LocalEndpoint).Port}/");

    private static async Task SendOversizedWebSocketMessageAsync(TcpListener listener, CancellationToken cancellationToken)
    {
        using var connection = await listener.AcceptTcpClientAsync(cancellationToken);
        await using var stream = connection.GetStream();
        var reader = new StreamReader(stream, Encoding.ASCII, leaveOpen: true);
        string? key = null;
        while (await reader.ReadLineAsync(cancellationToken) is { Length: > 0 } line)
        {
            if (line.StartsWith("Sec-WebSocket-Key:", StringComparison.OrdinalIgnoreCase))
                key = line.Split(':', 2)[1].Trim();
        }
        Assert.NotNull(key);
        // RFC 6455 requires SHA-1 for the WebSocket handshake, not for authenticating data.
        var accept = Convert.ToBase64String(SHA1.HashData(Encoding.ASCII.GetBytes(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")));
        await stream.WriteAsync(Encoding.ASCII.GetBytes($"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"), cancellationToken);
        using var socket = WebSocket.CreateFromStream(stream, isServer: true, subProtocol: null, Timeout.InfiniteTimeSpan);
        var fragment = new byte[65536];
        try
        {
            for (var sent = 0; sent <= ImmichRealtimeHttpClient.MaximumMessageBytes; sent += fragment.Length)
            {
                await socket.SendAsync(fragment, WebSocketMessageType.Binary, endOfMessage: false, cancellationToken);
            }
        }
        catch (WebSocketException)
        {
            // The client aborts as soon as it observes the over-limit fragment.
        }
    }

    private static async Task<string> ReplyOnceAsync(TcpListener listener, string response)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        using var connection = await listener.AcceptTcpClientAsync(timeout.Token);
        await using var stream = connection.GetStream();
        var buffer = new byte[8192];
        var count = 0;
        while (count < buffer.Length)
        {
            var read = await stream.ReadAsync(buffer.AsMemory(count), timeout.Token);
            if (read == 0) break;
            count += read;
            if (Encoding.ASCII.GetString(buffer, 0, count).Contains("\r\n\r\n", StringComparison.Ordinal)) break;
        }
        await stream.WriteAsync(Encoding.ASCII.GetBytes(response), timeout.Token);
        return Encoding.ASCII.GetString(buffer, 0, count);
    }
}
