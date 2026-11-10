using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using ImmichFolderWatch.Immich;

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
            while (true) await socket.ReceiveAsync(16384, timeout.Token);
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
        client.AddHeader("x-api-key", "synthetic-test-key");

        using var request = new HttpRequestMessage(HttpMethod.Get, origin);
        using var result = await client.SendAsync(request, CancellationToken.None);

        Assert.Equal(HttpStatusCode.Found, result.StatusCode);
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
        socket.AddHeader("x-api-key", "synthetic-test-key");
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
        using var request = new HttpRequestMessage(HttpMethod.Get, Address(server, "http"));

        await Assert.ThrowsAsync<HttpRequestException>(() => client.SendAsync(request, CancellationToken.None));
        await response;
    }

    [Fact]
    public async Task Transports_RejectCrossOriginAndDowngradeRequestsBeforeConnecting()
    {
        using var client = new ImmichRealtimeHttpClient(new Uri("https://immich.example.test/"));
        using var request = new HttpRequestMessage(HttpMethod.Get, "http://immich.example.test/socket.io");
        await Assert.ThrowsAsync<HttpRequestException>(() => client.SendAsync(request, CancellationToken.None));
        await Assert.ThrowsAsync<HttpRequestException>(() => client.GetStringAsync(new Uri("https://other.example.test/")));
        using var socket = new ImmichRealtimeWebSocket(new Uri("https://immich.example.test/"));
        await Assert.ThrowsAsync<HttpRequestException>(() => socket.ConnectAsync(new Uri("ws://immich.example.test/socket.io"), CancellationToken.None));
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
