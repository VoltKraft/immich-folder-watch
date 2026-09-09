using System.Diagnostics;
using System.Net.Sockets;
using ImmichFolderWatch.App.Linux.Platform;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.Tests.Core.Linux;

public sealed class DBusBackgroundPortalRequestTests
{
    [LinuxDBusFact]
    public async Task Session_GetAsyncHonorsCancellationAfterConnectionExists()
    {
        await using var portal = await TestPortal.StartAsync();
        await using var session = new DBusSession(portal.Address);
        await session.GetAsync();
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => session.GetAsync(cancelled.Token));
    }

    [LinuxDBusFact]
    public async Task Session_DisposeCancelsStalledConnectionAndQueuedCalls()
    {
        var socketPath = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "ifw-dbus-" + Guid.NewGuid().ToString("N"));
        using var listener = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
        listener.Bind(new UnixDomainSocketEndPoint(socketPath));
        listener.Listen(1);
        await using var session = new DBusSession("unix:path=" + socketPath);
        try
        {
            var connecting = session.GetAsync();
            using var socket = await listener.AcceptAsync().WaitAsync(TimeSpan.FromSeconds(5));
            var queued = session.GetAsync();
            await session.DisposeAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(5));
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => connecting);
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => queued);
            await Assert.ThrowsAsync<ObjectDisposedException>(() => session.GetAsync());
        }
        finally
        {
            File.Delete(socketPath);
        }
    }

    [LinuxDBusFact]
    public async Task RequestAsync_WaitsForSignalAndSendsSupportedOptions()
    {
        await using var portal = await TestPortal.StartAsync();
        await using var session = new DBusSession(portal.Address);
        var request = new DBusBackgroundPortalRequest(session, NullLogger<DBusBackgroundPortalRequest>.Instance);
        var pending = request.RequestAsync(true);
        var handle = await portal.Requested.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.False(pending.IsCompleted);
        Assert.True(portal.Options!["autostart"].GetBool());
        Assert.False(portal.Options.ContainsKey("background"));
        Assert.StartsWith("ifw_background_", portal.Options["handle_token"].GetString());
        portal.Respond(handle, new(0, true, true));
        Assert.Equal(new BackgroundPortalResponse(0, true, true), await pending.WaitAsync(TimeSpan.FromSeconds(5)));
    }

    [LinuxDBusFact]
    public async Task RequestAsync_ReceivesEarlyResponseOnLegacyHandle()
    {
        await using var portal = await TestPortal.StartAsync();
        portal.EarlyResponse = new(0, true, false);
        portal.UseLegacyHandle = true;
        await using var session = new DBusSession(portal.Address);
        var request = new DBusBackgroundPortalRequest(session, NullLogger<DBusBackgroundPortalRequest>.Instance);
        Assert.Equal(new BackgroundPortalResponse(0, true, false),
            await request.RequestAsync(false).WaitAsync(TimeSpan.FromSeconds(5)));
    }

    [LinuxDBusFact]
    public async Task RequestAsync_IgnoresUnrelatedSignalsAndParsesCancelledResponse()
    {
        await using var portal = await TestPortal.StartAsync();
        await using var session = new DBusSession(portal.Address);
        var request = new DBusBackgroundPortalRequest(session, NullLogger<DBusBackgroundPortalRequest>.Instance);
        var pending = request.RequestAsync(true);
        var handle = await portal.Requested.Task.WaitAsync(TimeSpan.FromSeconds(5));
        portal.Respond(handle + "_unrelated", new(0, true, true));
        portal.Respond(handle, new(1, false, false), omitPermissions: true);
        Assert.Equal(new BackgroundPortalResponse(1, false, false), await pending.WaitAsync(TimeSpan.FromSeconds(5)));
    }

    [LinuxDBusFact]
    public async Task RequestAsync_CallerCancellationClosesPortalRequest()
    {
        await using var portal = await TestPortal.StartAsync();
        await using var session = new DBusSession(portal.Address);
        var request = new DBusBackgroundPortalRequest(session, NullLogger<DBusBackgroundPortalRequest>.Instance);
        using var cancellation = new CancellationTokenSource();
        var pending = request.RequestAsync(true, cancellation.Token);
        var handle = await portal.Requested.Task.WaitAsync(TimeSpan.FromSeconds(5));
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.Equal(handle, await portal.Closed.Task.WaitAsync(TimeSpan.FromSeconds(5)));
    }

    [LinuxDBusFact]
    public async Task RequestAsync_TimeoutClosesPortalRequest()
    {
        await using var portal = await TestPortal.StartAsync();
        await using var session = new DBusSession(portal.Address);
        // Connect first so the deadline tests an unanswered portal interaction,
        // independently of process startup and session-bus connection speed.
        await session.GetAsync();
        var request = new DBusBackgroundPortalRequest(session, NullLogger<DBusBackgroundPortalRequest>.Instance)
        {
            ResponseTimeout = TimeSpan.FromSeconds(1),
        };
        var pending = request.RequestAsync(true);
        var handle = await portal.Requested.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await Assert.ThrowsAsync<TimeoutException>(() => pending.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.Equal(handle, await portal.Closed.Task.WaitAsync(TimeSpan.FromSeconds(5)));
    }

    [LinuxDBusFact]
    public async Task RequestAsync_PropagatesPortalMethodErrors()
    {
        await using var portal = await TestPortal.StartAsync();
        portal.MethodError = true;
        await using var session = new DBusSession(portal.Address);
        var request = new DBusBackgroundPortalRequest(session, NullLogger<DBusBackgroundPortalRequest>.Instance);
        var error = await Assert.ThrowsAnyAsync<DBusErrorReplyException>(() => request.RequestAsync(true).WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.Contains("Test denial", error.Message);
    }

    private sealed class TestPortal(Process bus, DBusConnection connection, string address) : IAsyncDisposable, IPathMethodHandler
    {
        public string Address { get; } = address;
        public string Path => "/org/freedesktop/portal/desktop";
        public bool HandlesChildPaths => true;
        public TaskCompletionSource<string> Requested { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource<string> Closed { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Dictionary<string, VariantValue>? Options { get; private set; }
        public BackgroundPortalResponse? EarlyResponse { get; set; }
        public bool UseLegacyHandle { get; set; }
        public bool MethodError { get; set; }

        public static async Task<TestPortal> StartAsync()
        {
            var bus = Process.Start(new ProcessStartInfo("/usr/bin/dbus-daemon")
            {
                ArgumentList = { "--session", "--nofork", "--nopidfile", "--print-address=1" },
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
            })!;
            DBusConnection? connection = null;
            try
            {
                var address = await bus.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5));
                Assert.False(string.IsNullOrEmpty(address));
                connection = new DBusConnection(address);
                await connection.ConnectAsync();
                await connection.RequestNameAsync("org.freedesktop.portal.Desktop");
                var portal = new TestPortal(bus, connection, address);
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
        }

        public ValueTask HandleMethodAsync(MethodContext context)
        {
            if (context.Request.MemberAsString == "Close")
            {
                Closed.TrySetResult(context.Request.PathAsString!);
                var closeReply = context.CreateReplyWriter(null);
                context.Reply(closeReply.CreateMessage());
                return ValueTask.CompletedTask;
            }
            if (MethodError)
            {
                context.ReplyError("org.freedesktop.portal.Error.NotAllowed", "Test denial");
                return ValueTask.CompletedTask;
            }
            var reader = context.Request.GetBodyReader();
            Assert.Equal(string.Empty, reader.ReadString());
            Options = reader.ReadDictionaryOfStringToVariantValue();
            var sender = context.Request.SenderAsString!.TrimStart(':').Replace('.', '_');
            var token = UseLegacyHandle ? "legacy_handle" : Options["handle_token"].GetString();
            var handle = $"{Path}/request/{sender}/{token}";
            if (EarlyResponse is { } early) Respond(handle, early);
            var reply = context.CreateReplyWriter("o");
            reply.WriteObjectPath(handle);
            context.Reply(reply.CreateMessage());
            Requested.TrySetResult(handle);
            return ValueTask.CompletedTask;
        }

        public void Respond(string handle, BackgroundPortalResponse response, bool omitPermissions = false)
        {
            var writer = connection.GetMessageWriter();
            writer.WriteSignalHeader(path: handle, @interface: "org.freedesktop.portal.Request", member: "Response", signature: "ua{sv}");
            writer.WriteUInt32(response.ResponseCode);
            writer.WriteDictionary(omitPermissions ? new Dictionary<string, VariantValue>() : new()
            {
                ["background"] = VariantValue.Bool(response.Background),
                ["autostart"] = VariantValue.Bool(response.Autostart),
            });
            Assert.True(connection.TrySendMessage(writer.CreateMessage()));
        }

        public async ValueTask DisposeAsync()
        {
            connection.Dispose();
            if (!bus.HasExited) bus.Kill();
            await bus.WaitForExitAsync();
            bus.Dispose();
        }
    }
}

public sealed class LinuxDBusFactAttribute : FactAttribute
{
    public LinuxDBusFactAttribute()
    {
        if (!OperatingSystem.IsLinux() || !File.Exists("/usr/bin/dbus-daemon"))
        {
            Skip = "Requires Linux and dbus-daemon for an isolated test bus; no live desktop is used.";
        }
    }
}
