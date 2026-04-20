using System.IO.Pipes;
using System.Security.Principal;
using System.Text;

namespace ImmichFolderWatch.App.Services;

public sealed class SingleInstanceCoordinator : IDisposable
{
    public const string ShowGuiSignal = "SHOW_GUI";

    private const string MutexNamePrefix = "Local\\ImmichFolderWatch-";
    private const string PipeNamePrefix = "ifw-";

    private readonly string _mutexName;
    private readonly string _pipeName;
    private readonly Mutex _mutex;
    private readonly bool _createdNew;

    private CancellationTokenSource? _listenerCts;
    private Task? _listenerTask;
    private Action? _onShowGuiRequested;

    private SingleInstanceCoordinator(string mutexName, string pipeName, Mutex mutex, bool createdNew)
    {
        _mutexName = mutexName;
        _pipeName = pipeName;
        _mutex = mutex;
        _createdNew = createdNew;
    }

    public static SingleInstanceCoordinator Create()
    {
        var userSid = GetUserSid();
        var mutexName = MutexNamePrefix + userSid;
        var pipeName = PipeNamePrefix + userSid;

        var mutex = new Mutex(initiallyOwned: true, name: mutexName, createdNew: out var createdNew);
        return new SingleInstanceCoordinator(mutexName, pipeName, mutex, createdNew);
    }

    public bool IsPrimaryInstance => _createdNew;

    public void StartListening(Action onShowGuiRequested)
    {
        ArgumentNullException.ThrowIfNull(onShowGuiRequested);

        if (!_createdNew)
        {
            throw new InvalidOperationException("Only the primary instance may listen for signals.");
        }

        if (_listenerTask is not null)
        {
            return;
        }

        _onShowGuiRequested = onShowGuiRequested;
        _listenerCts = new CancellationTokenSource();
        _listenerTask = Task.Run(() => RunListenerAsync(_listenerCts.Token));
    }

    public bool TrySignalShowGui(TimeSpan timeout)
    {
        if (_createdNew)
        {
            return false;
        }

        try
        {
            using var client = new NamedPipeClientStream(".", _pipeName, PipeDirection.Out);
            client.Connect((int)timeout.TotalMilliseconds);
            var payload = Encoding.UTF8.GetBytes(ShowGuiSignal);
            client.Write(payload, 0, payload.Length);
            client.Flush();
            return true;
        }
        catch (Exception)
        {
            return false;
        }
    }

    private async Task RunListenerAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                await using var server = new NamedPipeServerStream(
                    _pipeName,
                    PipeDirection.In,
                    maxNumberOfServerInstances: 1,
                    PipeTransmissionMode.Byte,
                    PipeOptions.Asynchronous);

                await server.WaitForConnectionAsync(cancellationToken);

                using var reader = new StreamReader(server, Encoding.UTF8);
                var message = await reader.ReadToEndAsync(cancellationToken);

                if (string.Equals(message?.Trim(), ShowGuiSignal, StringComparison.Ordinal))
                {
                    _onShowGuiRequested?.Invoke();
                }
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(250), cancellationToken);
            }
        }
    }

    private static string GetUserSid()
    {
        try
        {
            return WindowsIdentity.GetCurrent().User?.Value ?? Environment.UserName;
        }
        catch (Exception)
        {
            return Environment.UserName;
        }
    }

    public void Dispose()
    {
        try
        {
            _listenerCts?.Cancel();
            _listenerTask?.Wait(TimeSpan.FromSeconds(1));
        }
        catch (Exception)
        {
        }

        _listenerCts?.Dispose();

        if (_createdNew)
        {
            try
            {
                _mutex.ReleaseMutex();
            }
            catch (Exception)
            {
            }
        }

        _mutex.Dispose();
    }
}
