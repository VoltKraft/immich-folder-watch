using System.Net.WebSockets;
using SocketIOClient.Protocol.Http;
using SocketIOClient.Protocol.WebSocket;
using WebSocketMessageType = System.Net.WebSockets.WebSocketMessageType;

namespace ImmichFolderWatch.Immich;

/// <summary>Socket.IO polling transport with an origin boundary, no redirects and bounded responses.</summary>
public sealed class ImmichRealtimeHttpClient : IHttpClient, IDisposable
{
    public const int MaximumMessageBytes = 4 * 1024 * 1024;
    private readonly Uri _origin;
    private readonly HttpClientHandler _handler = new() { AllowAutoRedirect = false };
    private readonly HttpClient _client;
    private readonly CancellationToken _lifetimeToken;

    public ImmichRealtimeHttpClient(Uri origin, CancellationToken lifetimeToken = default)
    {
        _origin = origin;
        _lifetimeToken = lifetimeToken;
        _client = new HttpClient(_handler)
        {
            MaxResponseContentBufferSize = MaximumMessageBytes,
            Timeout = TimeSpan.FromMinutes(2),
        };
    }

    public void SetDefaultHeader(string name, string value)
    {
        _client.DefaultRequestHeaders.Remove(name);
        _client.DefaultRequestHeaders.Add(name, value);
    }

    public TimeSpan Timeout
    {
        get => _client.Timeout;
        set => _client.Timeout = value;
    }

    public async Task<IHttpResponse> SendAsync(HttpRequest request, CancellationToken cancellationToken)
    {
        RequireSameOrigin(_origin, request.Uri);
        using var message = new HttpRequestMessage(request.Method == RequestMethod.Get ? HttpMethod.Get : HttpMethod.Post, request.Uri);
        if (request.Method == RequestMethod.Post)
        {
            message.Content = request.BodyType == RequestBodyType.Bytes
                ? new ByteArrayContent(request.BodyBytes ?? [])
                : new StringContent(request.BodyText ?? string.Empty);
        }
        foreach (var header in request.Headers)
        {
            if (string.Equals(header.Key, "Content-Type", StringComparison.OrdinalIgnoreCase) && message.Content is not null)
            {
                message.Content.Headers.ContentType = System.Net.Http.Headers.MediaTypeHeaderValue.Parse(header.Value);
            }
            else
            {
                message.Headers.Add(header.Key, header.Value);
            }
        }

        // ResponseContentRead enforces the byte bound for declared and streamed bodies.
        // The upstream response interface has no disposal contract, so detach its bounded
        // contents here and release both native HTTP messages before handing it back.
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _lifetimeToken);
        using var response = await _client.SendAsync(message, linked.Token).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return new BufferedResponse(
            response.Content.Headers.ContentType?.MediaType,
            await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false),
            await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false));
    }

    private sealed record BufferedResponse(string? MediaType, byte[] Bytes, string Text) : IHttpResponse
    {
        public Task<byte[]> ReadAsByteArrayAsync() => Task.FromResult(Bytes);
        public Task<string> ReadAsStringAsync() => Task.FromResult(Text);
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
public sealed class ImmichRealtimeWebSocket : IWebSocketClient
{
    private readonly Uri _origin;
    private readonly ClientWebSocket _socket = new();
    private readonly SocketsHttpHandler _handler = new() { AllowAutoRedirect = false };
    private readonly HttpMessageInvoker _invoker;
    private int _messageBytes;
    private readonly CancellationTokenRegistration _lifetimeRegistration;

    public ImmichRealtimeWebSocket(Uri origin, CancellationToken lifetimeToken = default)
    {
        _origin = origin;
        _invoker = new HttpMessageInvoker(_handler);
        _lifetimeRegistration = lifetimeToken.Register(_socket.Abort);
    }

    public WebSocketState State => _socket.State;

    public Task ConnectAsync(Uri uri, CancellationToken cancellationToken)
    {
        ImmichRealtimeHttpClient.RequireSameOrigin(_origin, uri);
        return _socket.ConnectAsync(uri, _invoker, cancellationToken);
    }

    public Task CloseAsync(WebSocketCloseStatus closeStatus, string description, CancellationToken cancellationToken) =>
        _socket.CloseAsync(closeStatus, description, cancellationToken);

    public Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType type, bool endOfMessage, CancellationToken cancellationToken) =>
        _socket.SendAsync(buffer, type, endOfMessage, cancellationToken);

    public async Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken cancellationToken)
    {
        var result = await _socket.ReceiveAsync(buffer, cancellationToken).ConfigureAwait(false);
        if (result.Count > ImmichRealtimeHttpClient.MaximumMessageBytes - _messageBytes)
        {
            _socket.Abort();
            throw new WebSocketException("Realtime message exceeded the configured byte limit.");
        }
        _messageBytes = result.EndOfMessage ? 0 : _messageBytes + result.Count;
        return result;
    }

    public void SetDefaultHeader(string name, string value) => _socket.Options.SetRequestHeader(name, value);

    public void Dispose()
    {
        _lifetimeRegistration.Dispose();
        _socket.Dispose();
        _invoker.Dispose();
    }
}
