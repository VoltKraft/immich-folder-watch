using System.Collections.Concurrent;
using System.Diagnostics;
using ImmichFolderWatch.App.Linux.Platform;
using ImmichFolderWatch.Core.Platform;
using Microsoft.Extensions.Logging;
using Tmds.DBus.Protocol;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

public sealed class DBusNotifierTests
{
    [LinuxFact]
    public async Task ShowAsync_SendsVersionOnePortalPayloadAndPreservesIndependentNotifications()
    {
        await using var portal = await TestNotificationPortal.StartAsync();
        await using var session = new DBusSession(portal.Address);
        var logger = new RecordingLogger();
        var notifier = new DBusNotifier(session, logger);
        var priorities = new[] { "normal", "high", "urgent", "normal" };
        var kinds = new[] { NotificationKind.Info, NotificationKind.Warning, NotificationKind.Error, NotificationKind.Info };

        for (var i = 0; i < kinds.Length; i++)
        {
            await notifier.ShowAsync("Upload completed", "Photos/Urlaub ü.jpg", kinds[i], TestContext.Current.CancellationToken);
        }

        var requests = portal.Requests.ToArray();
        Assert.Equal(kinds.Length, requests.Length);
        Assert.Equal(kinds.Length, requests.Select(request => request.Id).Distinct().Count());
        for (var i = 0; i < requests.Length; i++)
        {
            var request = requests[i];
            Assert.Equal("org.freedesktop.portal.Desktop", request.Destination);
            Assert.Equal("org.freedesktop.portal.Notification", request.Interface);
            Assert.Equal("AddNotification", request.Method);
            Assert.Equal("sa{sv}", request.Signature);
            Assert.False(string.IsNullOrWhiteSpace(request.Id));
            Assert.Equal(3, request.Properties.Count);
            Assert.Equal("Upload completed", request.Properties["title"].GetString());
            Assert.Equal("Photos/Urlaub ü.jpg", request.Properties["body"].GetString());
            Assert.Equal(priorities[i], request.Properties["priority"].GetString());
        }
        Assert.Empty(logger.Entries);
    }

    [Fact]
    public async Task ShowAsync_PreCancelledRequestPropagatesWithoutLoggingDeliveryFailure()
    {
        await using var session = new DBusSession("unix:path=/nonexistent-ifw-test-bus");
        var logger = new RecordingLogger();
        var notifier = new DBusNotifier(session, logger);
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            notifier.ShowAsync("Upload", "Completed", cancellationToken: cancelled.Token));
        Assert.Empty(logger.Entries);
    }

    [LinuxFact]
    public async Task ShowAsync_CancellingPendingRequestPropagatesWithoutLoggingDeliveryFailure()
    {
        await using var portal = await TestNotificationPortal.StartAsync();
        portal.IgnoreRequest = true;
        await using var session = new DBusSession(portal.Address);
        var logger = new RecordingLogger();
        var notifier = new DBusNotifier(session, logger);
        using var cancelled = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        var pending = notifier.ShowAsync("Upload", "Completed", cancellationToken: cancelled.Token);
        await portal.FirstRequest.Task.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        cancelled.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            pending.WaitAsync(TimeSpan.FromSeconds(3), TestContext.Current.CancellationToken));
        Assert.Empty(logger.Entries);
    }

    [LinuxFact]
    public async Task ShowAsync_StalledPortalLogsTimeoutWithoutBlockingShutdown()
    {
        await using var portal = await TestNotificationPortal.StartAsync();
        portal.IgnoreRequest = true;
        await using var session = new DBusSession(portal.Address);
        var logger = new RecordingLogger();
        var notifier = new DBusNotifier(session, logger) { ResponseTimeout = TimeSpan.FromMilliseconds(100) };

        await notifier.ShowAsync("Upload", "Completed", cancellationToken: TestContext.Current.CancellationToken)
            .WaitAsync(TimeSpan.FromSeconds(3), TestContext.Current.CancellationToken);

        Assert.Single(portal.Requests);
        var entry = Assert.Single(logger.Entries);
        Assert.Equal(LogLevel.Warning, entry.Level);
        Assert.Contains("timed out", entry.Message);
    }

    [LinuxFact]
    public async Task ShowAsync_DeniedPortalLogsFailureWithoutThrowing()
    {
        await using var portal = await TestNotificationPortal.StartAsync();
        portal.DenyRequest = true;
        await using var session = new DBusSession(portal.Address);
        var logger = new RecordingLogger();
        var notifier = new DBusNotifier(session, logger);

        await notifier.ShowAsync("Upload", "Completed", cancellationToken: TestContext.Current.CancellationToken);

        var entry = Assert.Single(logger.Entries);
        Assert.Equal(LogLevel.Warning, entry.Level);
        Assert.NotNull(entry.Exception);
        Assert.Contains("org.freedesktop.portal.Error.NotAllowed", entry.Exception.Message);
        Assert.Contains("Failed to deliver notification", entry.Message);
    }

    [LinuxFact]
    public async Task ShowAsync_MissingPortalLogsFailureWithoutThrowing()
    {
        await using var portal = await TestNotificationPortal.StartAsync(ownName: false);
        await using var session = new DBusSession(portal.Address);
        var logger = new RecordingLogger();
        var notifier = new DBusNotifier(session, logger);

        await notifier.ShowAsync("Upload", "Completed", cancellationToken: TestContext.Current.CancellationToken);

        Assert.Empty(portal.Requests);
        var entry = Assert.Single(logger.Entries);
        Assert.Equal(LogLevel.Warning, entry.Level);
        Assert.NotNull(entry.Exception);
        Assert.Contains("org.freedesktop.DBus.Error.ServiceUnknown", entry.Exception.Message);
    }

    [LinuxFact]
    public async Task ShowAsync_FlatpakStyleBusFilterNeedsOnlyPortalAccess()
    {
        await using var portal = await TestNotificationPortal.StartAsync();
        var socketPath = Path.Combine(Path.GetTempPath(), "ifw-notification-" + Guid.NewGuid().ToString("N"));
        using var proxy = Process.Start(new ProcessStartInfo("/usr/bin/xdg-dbus-proxy")
        {
            ArgumentList = { portal.Address, socketPath, "--filter", "--talk=org.freedesktop.portal.Desktop" },
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            UseShellExecute = false,
        })!;
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(5));
            while (!File.Exists(socketPath)) await Task.Delay(10, timeout.Token);
            await using var session = new DBusSession("unix:path=" + socketPath);
            var logger = new RecordingLogger();
            var notifier = new DBusNotifier(session, logger);

            await notifier.ShowAsync("Upload", "Completed", cancellationToken: timeout.Token);

            Assert.Single(portal.Requests);
            Assert.Empty(logger.Entries);
        }
        finally
        {
            if (!proxy.HasExited) proxy.Kill();
            await proxy.WaitForExitAsync(TestContext.Current.CancellationToken);
            File.Delete(socketPath);
        }
    }

    private sealed class RecordingLogger : ILogger<DBusNotifier>
    {
        public ConcurrentQueue<(LogLevel Level, string Message, Exception? Exception)> Entries { get; } = new();
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel logLevel) => true;
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception,
            Func<TState, Exception?, string> formatter) => Entries.Enqueue((logLevel, formatter(state, exception), exception));
    }

    private sealed record NotificationRequest(string? Destination, string? Interface, string? Method,
        string? Signature, string Id, Dictionary<string, VariantValue> Properties);

    private sealed class TestNotificationPortal(Process bus, DBusConnection connection, string address)
        : IAsyncDisposable, IPathMethodHandler
    {
        private readonly ConcurrentQueue<MethodContext> _pendingRequests = new();
        public string Address { get; } = address;
        public string Path => "/org/freedesktop/portal/desktop";
        public bool HandlesChildPaths => false;
        public bool DenyRequest { get; set; }
        public bool IgnoreRequest { get; set; }
        public ConcurrentQueue<NotificationRequest> Requests { get; } = new();
        public TaskCompletionSource FirstRequest { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public static async Task<TestNotificationPortal> StartAsync(bool ownName = true)
        {
            // Exclude host service directories so a missing test portal cannot activate a real desktop service.
            var configPath = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "ifw-notification-bus-" + Guid.NewGuid().ToString("N"));
            await File.WriteAllTextAsync(configPath, """
                <busconfig>
                  <type>session</type>
                  <listen>unix:tmpdir=/tmp</listen>
                  <auth>EXTERNAL</auth>
                  <policy context="default">
                    <allow send_destination="*" eavesdrop="true"/>
                    <allow eavesdrop="true"/>
                    <allow own="*"/>
                  </policy>
                </busconfig>
                """, TestContext.Current.CancellationToken);
            var bus = Process.Start(new ProcessStartInfo("/usr/bin/dbus-daemon")
            {
                ArgumentList = { "--config-file=" + configPath, "--nofork", "--nopidfile", "--print-address=1" },
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
            })!;
            DBusConnection? connection = null;
            try
            {
                var address = await bus.StandardOutput.ReadLineAsync(TestContext.Current.CancellationToken)
                    .AsTask().WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
                Assert.NotNull(address);
                connection = new DBusConnection(address);
                await connection.ConnectAsync();
                if (ownName) await connection.RequestNameAsync("org.freedesktop.portal.Desktop");
                var portal = new TestNotificationPortal(bus, connection, address);
                connection.AddMethodHandler(portal);
                return portal;
            }
            catch
            {
                connection?.Dispose();
                if (!bus.HasExited) bus.Kill();
                bus.Dispose();
                throw;
            }
            finally
            {
                File.Delete(configPath);
            }
        }

        public ValueTask HandleMethodAsync(MethodContext context)
        {
            var request = context.Request;
            if (request.InterfaceAsString != "org.freedesktop.portal.Notification" ||
                request.MemberAsString != "AddNotification" || request.SignatureAsString != "sa{sv}")
            {
                context.ReplyError("org.freedesktop.DBus.Error.InvalidArgs", "Expected Notification.AddNotification(sa{sv})");
                return ValueTask.CompletedTask;
            }
            var reader = request.GetBodyReader();
            Requests.Enqueue(new NotificationRequest(request.DestinationAsString, request.InterfaceAsString,
                request.MemberAsString, request.SignatureAsString, reader.ReadString(), reader.ReadDictionaryOfStringToVariantValue()));
            if (IgnoreRequest)
            {
                // Returning an unhandled context normally generates an immediate UnknownMethod reply.
                context.DisposesAsynchronously = true;
                _pendingRequests.Enqueue(context);
                FirstRequest.TrySetResult();
                return ValueTask.CompletedTask;
            }
            FirstRequest.TrySetResult();
            if (DenyRequest)
            {
                context.ReplyError("org.freedesktop.portal.Error.NotAllowed", "Synthetic denied notification");
                return ValueTask.CompletedTask;
            }
            var reply = context.CreateReplyWriter(null);
            context.Reply(reply.CreateMessage());
            return ValueTask.CompletedTask;
        }

        public async ValueTask DisposeAsync()
        {
            while (_pendingRequests.TryDequeue(out var context)) context.Dispose();
            connection.Dispose();
            if (!bus.HasExited) bus.Kill();
            await bus.WaitForExitAsync(TestContext.Current.CancellationToken);
            bus.Dispose();
        }
    }
}
