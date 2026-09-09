using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;

namespace ImmichFolderWatch.App.Linux.Services;

/// <summary>
/// Keeps only the latest access check eligible to update the UI. Canceling or replacing
/// a check completes its wait even when the underlying checker ignores cancellation.
/// Callbacks resume on the caller's synchronization context and run only while current.
/// </summary>
public sealed class ImmichAccessCheckSession : IDisposable
{
    private readonly object _gate = new();
    private CancellationTokenSource? _current;
    private bool _disposed;

    public async Task RunAsync(
        AppConfig config,
        Func<AppConfig, CancellationToken, Task<ImmichAccessCheckResult>> verifyAsync,
        Action<ImmichAccessCheckResult> applyResult,
        Action<Exception> applyFailure,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentNullException.ThrowIfNull(verifyAsync);
        ArgumentNullException.ThrowIfNull(applyResult);
        ArgumentNullException.ThrowIfNull(applyFailure);

        CancellationTokenSource operation;
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            _current?.Cancel();
            operation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            _current = operation;
        }

        try
        {
            operation.Token.ThrowIfCancellationRequested();
            var check = verifyAsync(config, operation.Token);
            // A replaced checker may finish after its canceled WaitAsync has returned.
            // Observe a late failure without reporting stale errors to the current UI.
            _ = check.ContinueWith(static task => _ = task.Exception,
                CancellationToken.None,
                TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously,
                TaskScheduler.Default);
            var result = await check.WaitAsync(operation.Token);
            lock (_gate)
            {
                if (ReferenceEquals(_current, operation) && !operation.IsCancellationRequested)
                {
                    applyResult(result);
                }
            }
        }
        catch (OperationCanceledException) when (operation.IsCancellationRequested)
        {
        }
        catch (Exception ex)
        {
            lock (_gate)
            {
                if (ReferenceEquals(_current, operation) && !operation.IsCancellationRequested)
                {
                    applyFailure(ex);
                }
            }
        }
        finally
        {
            lock (_gate)
            {
                if (ReferenceEquals(_current, operation))
                {
                    _current = null;
                }
                operation.Dispose();
            }
        }
    }

    /// <summary>Invalidates any in-flight result without waiting for its network request.</summary>
    public void Cancel()
    {
        lock (_gate)
        {
            _current?.Cancel();
            _current = null;
        }
    }

    public void Dispose()
    {
        lock (_gate)
        {
            if (_disposed)
            {
                return;
            }
            _disposed = true;
            _current?.Cancel();
            _current = null;
        }
    }
}
