using System.Collections.Concurrent;
using ImmichFolderWatch.Core.Platform;

namespace ImmichFolderWatch.Tests.Core.ViewModels;

/// <summary>Runs UI-affine tests and their await continuations on one dedicated thread.</summary>
internal sealed class SingleThreadUiContext : SynchronizationContext, IUiDispatcher
{
    private readonly BlockingCollection<(SendOrPostCallback Callback, object? State)> _callbacks = new();
    private readonly int _threadId = Environment.CurrentManagedThreadId;
    private int _stopped;

    public bool IsOnUiThread => Environment.CurrentManagedThreadId == _threadId;

    public void Post(Action action) => Post(_ => action(), null);

    public override void Post(SendOrPostCallback callback, object? state)
    {
        if (Volatile.Read(ref _stopped) != 0)
        {
            return;
        }
        try
        {
            _callbacks.Add((callback, state));
        }
        catch (InvalidOperationException)
        {
            // A timed-out or failed test may still have an outstanding continuation.
        }
    }

    public static Task RunAsync(Func<IUiDispatcher, Task> test)
    {
        var completed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var thread = new Thread(() =>
        {
            var context = new SingleThreadUiContext();
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            Exception? failure = null;
            SetSynchronizationContext(context);
            context.Post(async _ =>
            {
                try
                {
                    await test(context);
                }
                catch (Exception exception)
                {
                    failure = exception;
                }
                finally
                {
                    context._callbacks.CompleteAdding();
                }
            }, null);
            try
            {
                foreach (var (callback, state) in context._callbacks.GetConsumingEnumerable(timeout.Token))
                {
                    callback(state);
                }
            }
            catch (OperationCanceledException)
            {
                failure = new TimeoutException("The UI test did not finish within 30 seconds.");
            }
            catch (Exception exception)
            {
                failure = exception;
            }
            finally
            {
                Volatile.Write(ref context._stopped, 1);
                SetSynchronizationContext(null);
                context._callbacks.Dispose();
            }
            if (failure is null)
            {
                completed.SetResult();
            }
            else
            {
                completed.SetException(failure);
            }
        }) { IsBackground = true, Name = "Platform parity test UI" };
        thread.Start();
        return completed.Task;
    }
}
