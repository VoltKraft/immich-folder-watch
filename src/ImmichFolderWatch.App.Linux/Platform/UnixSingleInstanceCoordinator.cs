using System.Net.Sockets;
using System.Text;
using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class UnixSingleInstanceCoordinator : ISingleInstanceCoordinator
{
    public const string ShowGuiSignal = "SHOW_GUI";
    public const string DefaultSocketName = "immich-folder-watch.sock";

    private readonly string _socketPath;
    private readonly ILogger<UnixSingleInstanceCoordinator> _logger;
    private readonly Socket? _serverSocket;
    private readonly LinuxPrivateDirectory _directory;
    private readonly bool _isPrimary;
    private CancellationTokenSource? _listenCts;
    private bool _disposed;

    public UnixSingleInstanceCoordinator()
        : this(GetDefaultSocketPath(), NullLogger<UnixSingleInstanceCoordinator>.Instance)
    {
    }

    public UnixSingleInstanceCoordinator(string socketPath)
        : this(socketPath, NullLogger<UnixSingleInstanceCoordinator>.Instance)
    {
    }

    public UnixSingleInstanceCoordinator(string socketPath, ILogger<UnixSingleInstanceCoordinator> logger)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(socketPath);
        if (!OperatingSystem.IsLinux())
        {
            throw new PlatformNotSupportedException("Unix instance coordination requires Linux.");
        }
        _socketPath = socketPath;
        _logger = logger;

        var endpoint = new UnixDomainSocketEndPoint(_socketPath);
        _directory = LinuxPrivateDirectory.Open(Path.GetDirectoryName(Path.GetFullPath(_socketPath))!);
        Socket? server = null;
        try
        {
            server = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
            try
            {
                server.Bind(endpoint);
            }
            catch (SocketException ex) when (ex.SocketErrorCode == SocketError.AddressAlreadyInUse)
            {
                server.Dispose();
                if (!TryReclaimStaleSocket(endpoint))
                {
                    _isPrimary = false;
                    return;
                }
                server = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
                server.Bind(endpoint);
            }
            server.Listen(1);
            _serverSocket = server;
            _isPrimary = true;
        }
        catch
        {
            server?.Dispose();
            if (OperatingSystem.IsLinux())
            {
                _directory.Dispose();
            }
            throw;
        }
    }

    public bool IsPrimaryInstance => _isPrimary;

    public void StartListening(Action onShowGuiRequested)
    {
        ArgumentNullException.ThrowIfNull(onShowGuiRequested);
        if (!_isPrimary || _serverSocket is null)
        {
            return;
        }

        _listenCts = new CancellationTokenSource();
        _ = AcceptLoopAsync(_serverSocket, onShowGuiRequested, _listenCts.Token);
    }

    private async Task AcceptLoopAsync(Socket server, Action onShowGuiRequested, CancellationToken cancellationToken)
    {
        var buffer = new byte[64];
        while (!cancellationToken.IsCancellationRequested)
        {
            Socket client;
            try
            {
                client = await server.AcceptAsync(cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                return;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "UDS accept failed");
                return;
            }

            try
            {
                var read = await client.ReceiveAsync(buffer, SocketFlags.None, cancellationToken).ConfigureAwait(false);
                var payload = Encoding.UTF8.GetString(buffer, 0, read).Trim();
                if (string.Equals(payload, ShowGuiSignal, StringComparison.Ordinal))
                {
                    onShowGuiRequested();
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "UDS read failed");
            }
            finally
            {
                client.Dispose();
            }
        }
    }

    public bool TrySignalShowGui(TimeSpan timeout)
    {
        if (_isPrimary)
        {
            return false;
        }

        try
        {
            using var client = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
            using var cts = new CancellationTokenSource(timeout);
            var endpoint = new UnixDomainSocketEndPoint(_socketPath);
            var connectTask = client.ConnectAsync(endpoint, cts.Token).AsTask();
            connectTask.Wait(cts.Token);
            var payload = Encoding.UTF8.GetBytes(ShowGuiSignal);
            client.Send(payload);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to signal primary instance via {Path}", _socketPath);
            return false;
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _listenCts?.Cancel();
        _listenCts?.Dispose();
        _serverSocket?.Dispose();
        if (_isPrimary)
        {
            TryDeleteSocketFile(_socketPath);
        }
        if (OperatingSystem.IsLinux())
        {
            _directory.Dispose();
        }
    }

    private static string GetDefaultSocketPath()
    {
        var runtime = Environment.GetEnvironmentVariable("XDG_RUNTIME_DIR");
        if (string.IsNullOrWhiteSpace(runtime))
        {
            runtime = Path.Combine(new XdgPlatformPaths().GetUserDataRoot(), "runtime");
        }
        return Path.Combine(runtime, DefaultSocketName);
    }

    private bool TryReclaimStaleSocket(UnixDomainSocketEndPoint endpoint)
    {
        try
        {
            using var probe = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
            probe.Connect(endpoint);
            return false;
        }
        catch (SocketException ex) when (ex.SocketErrorCode == SocketError.ConnectionRefused)
        {
            TryDeleteSocketFile(_socketPath);
            return true;
        }
    }

    private static void TryDeleteSocketFile(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
        }
    }
}
