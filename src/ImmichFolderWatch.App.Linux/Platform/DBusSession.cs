using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class DBusSession : IAsyncDisposable
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly CancellationTokenSource _disposeCancellation = new();
    private readonly string? _address;
    private DBusConnection? _connection;
    private int _disposed;

    public DBusSession()
    {
    }

    /// <summary>Connects to an explicit bus address, useful for an isolated integration-test bus.</summary>
    public DBusSession(string address)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(address);
        _address = address;
    }

    /// <summary>Returns the shared session connection, connecting on first use.</summary>
    /// <exception cref="OperationCanceledException">The caller cancels or session disposal cancels a pending wait.</exception>
    /// <exception cref="ObjectDisposedException">The session is disposed, including when a queued caller acquires the gate during disposal.</exception>
    public async Task<DBusConnection> GetAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _disposeCancellation.Token);
        await _gate.WaitAsync(linked.Token).ConfigureAwait(false);
        try
        {
            ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
            if (_connection is null)
            {
                var address = _address ?? DBusAddress.Session
                    ?? throw new InvalidOperationException(
                        "No D-Bus session bus address. Set DBUS_SESSION_BUS_ADDRESS or run inside a desktop session.");
                var connection = new DBusConnection(address);
                try
                {
                    await connection.ConnectAsync().AsTask().WaitAsync(linked.Token).ConfigureAwait(false);
                    linked.Token.ThrowIfCancellationRequested();
                    ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
                    _connection = connection;
                }
                catch
                {
                    connection.Dispose();
                    throw;
                }
            }

            return _connection;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
        }

        _disposeCancellation.Cancel();
        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            _connection?.Dispose();
            _connection = null;
            _disposeCancellation.Dispose();
        }
        finally
        {
            // Already queued GetAsync callers must be able to acquire and release
            // the gate before observing disposal. No wait handle is allocated here.
            _gate.Release();
        }
    }
}
