using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

public sealed class DBusSession : IAsyncDisposable
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private DBusConnection? _connection;

    public async Task<DBusConnection> GetAsync(CancellationToken cancellationToken = default)
    {
        if (_connection is not null)
        {
            return _connection;
        }

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_connection is null)
            {
                var address = DBusAddress.Session
                    ?? throw new InvalidOperationException(
                        "No D-Bus session bus address. Set DBUS_SESSION_BUS_ADDRESS or run inside a desktop session.");
                var connection = new DBusConnection(address);
                await connection.ConnectAsync().ConfigureAwait(false);
                _connection = connection;
            }
        }
        finally
        {
            _gate.Release();
        }

        return _connection;
    }

    public ValueTask DisposeAsync()
    {
        _connection?.Dispose();
        _connection = null;
        _gate.Dispose();
        return ValueTask.CompletedTask;
    }
}
