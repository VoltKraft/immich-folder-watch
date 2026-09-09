using System.Diagnostics;
using ImmichFolderWatch.App.Linux.Platform;
using Tmds.DBus.Protocol;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

public sealed class StatusNotifierItemTests
{
    [Fact]
    public async Task RegistersUnderApplicationNamespaceAndExportsIconAndMenu()
    {
        await using var bus = await TestBus.StartAsync();
        using var item = new StatusNotifierItem(bus.Address, 1, 1, [255, 12, 34, 56]);
        item.Update("Connected", "Open", "Restart", "Quit");
        await item.StartAsync(TestContext.Current.CancellationToken);
        Assert.True(item.IsRegistered);
        Assert.Equal(StatusNotifierItem.BusName, await bus.Registered.Task.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken));
        var props = await bus.GetPropertiesAsync("/StatusNotifierItem", StatusNotifierItem.ItemInterface);
        Assert.Equal("Active", props["Status"].GetString());
        Assert.Equal("Connected", props["Title"].GetString());
        Assert.Equal(StatusNotifierItem.MenuPath, props["Menu"].GetObjectPath().ToString());
        Assert.Equal(new byte[] { 255, 12, 34, 56 }, props["IconPixmap"].GetItem(0).GetItem(2).GetArray<byte>());
        Assert.Equal("Connected", props["ToolTip"].GetItem(3).GetString());
        var layout = await bus.GetLayoutAsync();
        Assert.Equal(new[] { "Open", "Restart", "Quit" }, layout);
    }

    [Fact]
    public async Task MenuEventsDispatchActionsAndLanguageChangesUpdateLayout()
    {
        await using var bus = await TestBus.StartAsync();
        using var item = new StatusNotifierItem(bus.Address, 1, 1, [255, 0, 0, 0]);
        await item.StartAsync(TestContext.Current.CancellationToken);
        var actions = new List<int>();
        var completed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        item.Activated += id => { actions.Add(id); if (id == 3) completed.TrySetResult(); };
        for (var id = 1; id <= 3; id++) await bus.ClickAsync(id);
        await completed.Task.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        Assert.Equal(new[] { 1, 2, 3 }, actions);
        item.Update("Verbunden", "Öffnen", "Neustart", "Beenden");
        Assert.Equal(new[] { "Öffnen", "Neustart", "Beenden" }, await bus.GetLayoutAsync());
    }

    [Fact]
    public async Task MissingWatcherKeepsUnregisteredAndWatcherRecoveryRegistersAgain()
    {
        await using var bus = await TestBus.StartAsync(ownWatcher: false);
        using var item = new StatusNotifierItem(bus.Address, 1, 1, [255, 0, 0, 0]);
        await item.StartAsync(TestContext.Current.CancellationToken);
        Assert.False(item.IsRegistered);
        var available = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        item.AvailabilityChanged += value => { if (value) available.TrySetResult(); };
        await bus.Connection.RequestNameAsync(StatusNotifierItem.Watcher);
        await available.Task.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        Assert.True(item.IsRegistered);
    }

    [Fact]
    public async Task FlatpakStyleBusFilterAllowsRegistrationAndMenuWithoutKdeOwnership()
    {
        await using var bus = await TestBus.StartAsync();
        var socketPath = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "ifw-tray-" + Guid.NewGuid().ToString("N"));
        using var proxy = Process.Start(new ProcessStartInfo("/usr/bin/xdg-dbus-proxy")
        {
            ArgumentList = { bus.Address, socketPath, "--filter", "--own=io.github.voltkraft.immich-folder-watch.*", "--talk=org.kde.StatusNotifierWatcher" },
            RedirectStandardError = true, RedirectStandardOutput = true, UseShellExecute = false,
        })!;
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(5));
            while (!File.Exists(socketPath)) await Task.Delay(10, timeout.Token);
            using var item = new StatusNotifierItem("unix:path=" + socketPath, 1, 1, [255, 12, 34, 56]);
            item.Update("Connected", "Open", "Restart", "Quit");
            await item.StartAsync(timeout.Token);
            Assert.True(item.IsRegistered);
            Assert.Equal(StatusNotifierItem.BusName, await bus.Registered.Task.WaitAsync(timeout.Token));
            Assert.Equal(new[] { "Open", "Restart", "Quit" }, await bus.GetLayoutAsync().WaitAsync(timeout.Token));
            var action = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
            item.Activated += id => action.TrySetResult(id);
            await bus.ClickAsync(2).WaitAsync(timeout.Token);
            Assert.Equal(2, await action.Task.WaitAsync(timeout.Token));
        }
        finally
        {
            if (!proxy.HasExited) proxy.Kill();
            await proxy.WaitForExitAsync(TestContext.Current.CancellationToken);
            File.Delete(socketPath);
        }
    }

    [Fact]
    public async Task DelayedRegistrationReplyCannotRestoreAvailabilityAfterWatcherDisappears()
    {
        await using var bus = await TestBus.StartAsync();
        bus.RegistrationGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var item = new StatusNotifierItem(bus.Address, 1, 1, [255, 0, 0, 0]);
        var unavailable = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        item.AvailabilityChanged += available => { if (!available) unavailable.TrySetResult(); };
        var starting = item.StartAsync(TestContext.Current.CancellationToken);
        await bus.Registered.Task.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        await bus.Connection.ReleaseNameAsync(StatusNotifierItem.Watcher);
        await unavailable.Task.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        bus.RegistrationGate.SetResult();
        await starting.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        Assert.False(item.IsRegistered);
    }

    [Fact]
    public async Task DisposingWithdrawsBusNameAndStopsExporting()
    {
        await using var bus = await TestBus.StartAsync();
        var item = new StatusNotifierItem(bus.Address, 1, 1, [255, 0, 0, 0]);
        await item.StartAsync(TestContext.Current.CancellationToken);
        item.Dispose();
        Assert.False(item.IsRegistered);
        var error = await Assert.ThrowsAnyAsync<DBusErrorReplyException>(() => bus.GetPropertiesAsync("/StatusNotifierItem", StatusNotifierItem.ItemInterface));
        Assert.Contains("org.freedesktop.DBus.Error.ServiceUnknown", error.Message);
    }

    private sealed class TestBus(Process process, DBusConnection connection, string address) : IAsyncDisposable, IPathMethodHandler
    {
        public DBusConnection Connection => connection;
        public string Address => address;
        public string Path => "/StatusNotifierWatcher";
        public bool HandlesChildPaths => false;
        public TaskCompletionSource? RegistrationGate { get; set; }
        public TaskCompletionSource<string> Registered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public static async Task<TestBus> StartAsync(bool ownWatcher = true)
        {
            var process = Process.Start(new ProcessStartInfo("/usr/bin/dbus-daemon")
            {
                ArgumentList = { "--session", "--nofork", "--nopidfile", "--print-address=1" },
                RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false,
            })!;
            var address = await process.StandardOutput.ReadLineAsync(TestContext.Current.CancellationToken);
            Assert.NotNull(address);
            var connection = new DBusConnection(address);
            await connection.ConnectAsync();
            if (ownWatcher) await connection.RequestNameAsync(StatusNotifierItem.Watcher);
            var bus = new TestBus(process, connection, address);
            connection.AddMethodHandler(bus);
            return bus;
        }
        public async ValueTask HandleMethodAsync(MethodContext context)
        {
            Registered.TrySetResult(context.Request.GetBodyReader().ReadString());
            if (RegistrationGate is { } gate) await gate.Task.ConfigureAwait(false);
            var writer = context.CreateReplyWriter(null); context.Reply(writer.CreateMessage());
        }
        public Task<Dictionary<string, VariantValue>> GetPropertiesAsync(string path, string iface)
        {
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(destination: StatusNotifierItem.BusName, path: path,
                @interface: "org.freedesktop.DBus.Properties", member: "GetAll", signature: "s");
            writer.WriteString(iface);
            return connection.CallMethodAsync(writer.CreateMessage(), static (message, _) => message.GetBodyReader().ReadDictionaryOfStringToVariantValue(), null);
        }
        public Task<string[]> GetLayoutAsync()
        {
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(destination: StatusNotifierItem.BusName, path: StatusNotifierItem.MenuPath,
                @interface: StatusNotifierItem.MenuInterface, member: "GetLayout", signature: "iias");
            writer.WriteInt32(0); writer.WriteInt32(-1); writer.WriteArray(System.Array.Empty<string>());
            return connection.CallMethodAsync(writer.CreateMessage(), static (message, _) =>
            {
                var reader = message.GetBodyReader();
                _ = reader.ReadUInt32(); reader.AlignStruct(); _ = reader.ReadInt32(); _ = reader.ReadDictionaryOfStringToVariantValue();
                return reader.ReadArrayOfVariantValue().Select(node => node.GetItem(1).GetDictionary<string, VariantValue>()["label"].GetString()).ToArray();
            }, null);
        }
        public Task ClickAsync(int id)
        {
            var writer = connection.GetMessageWriter();
            writer.WriteMethodCallHeader(destination: StatusNotifierItem.BusName, path: StatusNotifierItem.MenuPath,
                @interface: StatusNotifierItem.MenuInterface, member: "Event", signature: "isvu");
            writer.WriteInt32(id); writer.WriteString("clicked"); writer.WriteVariantInt32(0); writer.WriteUInt32(0);
            return connection.CallMethodAsync(writer.CreateMessage());
        }
        public async ValueTask DisposeAsync()
        {
            connection.Dispose();
            if (!process.HasExited) process.Kill();
            await process.WaitForExitAsync(TestContext.Current.CancellationToken);
            process.Dispose();
        }
    }
}
