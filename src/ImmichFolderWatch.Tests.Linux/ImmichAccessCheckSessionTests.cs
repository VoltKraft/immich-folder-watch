using ImmichFolderWatch.App.Linux.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

public sealed class ImmichAccessCheckSessionTests
{
    [Fact]
    public async Task ReplacingSlowCheck_OnlyAppliesNewestResult()
    {
        using var session = new ImmichAccessCheckSession();
        var oldCheck = new TaskCompletionSource<ImmichAccessCheckResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        var newest = new ImmichAccessCheckResult { UrlState = CheckState.Passed };
        var applied = new List<ImmichAccessCheckResult>();
        var failures = new List<Exception>();
        var oldRun = session.RunAsync(new AppConfig(), (_, _) => oldCheck.Task, applied.Add, failures.Add, TestContext.Current.CancellationToken);

        await session.RunAsync(new AppConfig(), (_, _) => Task.FromResult(newest), applied.Add, failures.Add, TestContext.Current.CancellationToken);
        await oldRun.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
        oldCheck.SetResult(new ImmichAccessCheckResult { UrlState = CheckState.Failed });

        Assert.Same(newest, Assert.Single(applied));
        Assert.Empty(failures);
    }

    [Fact]
    public async Task CancelForSave_CompletesWaitWithoutWaitingForUncooperativeChecker()
    {
        using var session = new ImmichAccessCheckSession();
        var check = new TaskCompletionSource<ImmichAccessCheckResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        var applied = new List<ImmichAccessCheckResult>();
        var failures = new List<Exception>();
        var run = session.RunAsync(new AppConfig(), (_, _) => check.Task, applied.Add, failures.Add, TestContext.Current.CancellationToken);

        session.Cancel();
        await run.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
        Assert.False(check.Task.IsCompleted);
        check.SetException(new IOException("Old request failed after Save started."));
        await Assert.ThrowsAsync<IOException>(() => check.Task);

        Assert.Empty(applied);
        Assert.Empty(failures);
    }

    [Fact]
    public async Task LatestFailure_IsReported_AndNewChecksRemainUsable()
    {
        using var session = new ImmichAccessCheckSession();
        var failure = new IOException("Synthetic current failure.");
        var applied = new List<ImmichAccessCheckResult>();
        var failures = new List<Exception>();
        await session.RunAsync(new AppConfig(), (_, _) => Task.FromException<ImmichAccessCheckResult>(failure),
            applied.Add, failures.Add, TestContext.Current.CancellationToken);
        await session.RunAsync(new AppConfig(), (_, _) => Task.FromResult(new ImmichAccessCheckResult()),
            applied.Add, failures.Add, TestContext.Current.CancellationToken);

        Assert.Same(failure, Assert.Single(failures));
        Assert.Single(applied);
    }

    [Fact]
    public async Task ShutdownCancellation_SuppressesResultsAndErrors()
    {
        using var session = new ImmichAccessCheckSession();
        using var shutdown = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        var check = new TaskCompletionSource<ImmichAccessCheckResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        var applied = new List<ImmichAccessCheckResult>();
        var failures = new List<Exception>();
        var run = session.RunAsync(new AppConfig(), (_, _) => check.Task, applied.Add, failures.Add, shutdown.Token);

        shutdown.Cancel();
        await run.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
        check.SetResult(new ImmichAccessCheckResult());

        Assert.Empty(applied);
        Assert.Empty(failures);
    }
}
