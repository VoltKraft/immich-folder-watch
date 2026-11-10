using System.Net;
using System.Net.WebSockets;
using SocketIOClient.Transport;
using SocketIOClient.Transport.Http;
using SocketIOClient.Transport.WebSockets;
using SocketWebSocketState = SocketIOClient.Transport.WebSockets.WebSocketState;
using SocketReceiveResult = SocketIOClient.Transport.WebSockets.WebSocketReceiveResult;

namespace ImmichFolderWatch.Immich;

/// <summary>Socket.IO polling transport with an origin boundary, no redirects and bounded responses.</summary>
public sealed class ImmichRealtimeHttpClient : IHttpClient
{
    public const int MaximumMessageBytes = 4 * 1024 * 1024;
    private readonly Uri _origin;
    private readonly HttpClientHandler _handler = new() { AllowAutoRedirect = false };
    private readonly HttpClient _client;

    public ImmichRealtimeHttpClient(Uri origin)
    {
        _origin = origin;
        _client = new HttpClient(_handler)
        {
            MaxResponseContentBufferSize = MaximumMessageBytes,
            Timeout = TimeSpan.FromMinutes(2),
        };
    }

    public void AddHeader(string name, string value)
    {
        _client.DefaultRequestHeaders.Remove(name);
        _client.DefaultRequestHeaders.Add(name, value);
    }

    public void SetProxy(IWebProxy proxy) => _handler.Proxy = proxy;

    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        RequireSameOrigin(_origin, request.RequestUri);
        return _client.SendAsync(request, cancellationToken);
    }

    public Task<HttpResponseMessage> PostAsync(string requestUri, HttpContent content, CancellationToken cancellationToken)
    {
        RequireSameOrigin(_origin, new Uri(requestUri, UriKind.Absolute));
        return _client.PostAsync(requestUri, content, cancellationToken);
    }

    public Task<string> GetStringAsync(Uri requestUri)
    {
        RequireSameOrigin(_origin, requestUri);
        return _client.GetStringAsync(requestUri);
    }

    public void Dispose() => _client.Dispose();

    internal static void RequireSameOrigin(Uri origin, Uri? target)
    {
        var expectedScheme = origin.Scheme == Uri.UriSchemeHttps ? Uri.UriSchemeWss : Uri.UriSchemeWs;
        if (target is null || !target.IsAbsoluteUri || !string.IsNullOrEmpty(target.UserInfo)
            || (target.Scheme != origin.Scheme && target.Scheme != expectedScheme)
            || !string.Equals(target.Host, origin.Host, StringComparison.OrdinalIgnoreCase)
            || target.Port != origin.Port)
        {
            throw new HttpRequestException("Realtime requests must remain on the configured Immich origin.");
        }
    }
}

/// <summary>Socket.IO WebSocket adapter that rejects redirects and oversized fragmented messages.</summary>
public sealed class ImmichRealtimeWebSocket : IClientWebSocket
{
    private readonly Uri _origin;
    private readonly ClientWebSocket _socket = new();
    private readonly SocketsHttpHandler _handler = new() { AllowAutoRedirect = false };
    private readonly HttpMessageInvoker _invoker;
    private int _messageBytes;

    public ImmichRealtimeWebSocket(Uri origin)
    {
        _origin = origin;
        _invoker = new HttpMessageInvoker(_handler);
    }

    public SocketWebSocketState State => (SocketWebSocketState)_socket.State;

    public Task ConnectAsync(Uri uri, CancellationToken cancellationToken)
    {
        ImmichRealtimeHttpClient.RequireSameOrigin(_origin, uri);
        return _socket.ConnectAsync(uri, _invoker, cancellationToken);
    }

    public Task DisconnectAsync(CancellationToken cancellationToken) =>
        _socket.CloseAsync(WebSocketCloseStatus.NormalClosure, string.Empty, cancellationToken);

    public Task SendAsync(byte[] bytes, TransportMessageType type, bool endOfMessage, CancellationToken cancellationToken) =>
        _socket.SendAsync(new ArraySegment<byte>(bytes), (WebSocketMessageType)type, endOfMessage, cancellationToken);

    public async Task<SocketReceiveResult> ReceiveAsync(int bufferSize, CancellationToken cancellationToken)
    {
        var buffer = new byte[Math.Clamp(bufferSize, 1, 65536)];
        var result = await _socket.ReceiveAsync(new ArraySegment<byte>(buffer), cancellationToken).ConfigureAwait(false);
        if (result.Count > ImmichRealtimeHttpClient.MaximumMessageBytes - _messageBytes)
        {
            _socket.Abort();
            throw new WebSocketException("Realtime message exceeded the configured byte limit.");
        }
        _messageBytes = result.EndOfMessage ? 0 : _messageBytes + result.Count;
        return new SocketReceiveResult
        {
            Buffer = buffer,
            Count = result.Count,
            EndOfMessage = result.EndOfMessage,
            MessageType = (TransportMessageType)result.MessageType,
        };
    }

    public void AddHeader(string name, string value) => _socket.Options.SetRequestHeader(name, value);
    public void SetProxy(IWebProxy proxy) => _handler.Proxy = proxy;

    public void Dispose()
    {
        _socket.Dispose();
        _invoker.Dispose();
    }
}
