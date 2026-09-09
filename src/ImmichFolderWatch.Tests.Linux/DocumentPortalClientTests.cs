using System.Diagnostics;
using System.Text;
using ImmichFolderWatch.App.Linux.Platform;
using Microsoft.Extensions.Logging.Abstractions;
using Tmds.DBus.Protocol;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

public sealed class DocumentPortalClientTests
{
    [Theory]
    [InlineData("/home/example/Photos", "/Photos", "/home/example/Photos")]
    [InlineData("/home/example/Photos", "/Photos/2026/Holiday", "/home/example/Photos/2026/Holiday")]
    [InlineData("/home/example/Urlaub ü", "/Urlaub ü", "/home/example/Urlaub ü")]
    [InlineData("/home/example/Photos", "", "/home/example/Photos")]
    [InlineData("/home/example/Photos", "/Other", null)]
    [InlineData("/home/example/Photos", "/Photos/../Private", null)]
    [InlineData("relative", "/Photos", null)]
    public void MapDocumentPath_KeepsOnlyThePathInsideTheGrantedDocument(string host, string suffix, string? expected)
        => Assert.Equal(expected, DocumentPortalClient.MapDocumentPath(host, suffix));

    [Fact]
    public async Task ResolveHostPathAsync_AttributeResolvesExactNestedPathWithoutABus()
    {
        await using var session = new DBusSession("unix:path=/nonexistent-ifw-test-bus");
        var client = new DocumentPortalClient(session, NullLogger<DocumentPortalClient>.Instance,
            path => path.EndsWith("/Photos/Sub", StringComparison.Ordinal) ? "/home/example/Photos/Sub" : null);
        Assert.Equal("/home/example/Photos/Sub", await client.ResolveHostPathAsync(
            "/run/user/1000/doc/opaque-ID_123/Photos/Sub", TestContext.Current.CancellationToken));
        Assert.Null(await client.ResolveHostPathAsync("/home/example/Photos", TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task ResolveHostPathAsync_CancellationIsNotReportedAsAnUnresolvedPath()
    {
        await using var session = new DBusSession("unix:path=/nonexistent-ifw-test-bus");
        var client = new DocumentPortalClient(session);
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => client.ResolveHostPathAsync(
            "/run/user/1000/doc/abcd/Photos", cancelled.Token));
    }

    [LinuxFact]
    public async Task ResolveHostPathAsync_UsesSandboxAccessibleGetHostPathsAndParsesByteStringDictionary()
    {
        await using var portal = await TestDocumentsPortal.StartAsync();
        await using var session = new DBusSession(portal.Address);
        var client = new DocumentPortalClient(session, NullLogger<DocumentPortalClient>.Instance, _ => null);
        Assert.Equal("/home/example/Photos/Nested", await client.ResolveHostPathAsync(
            "/run/user/1000/doc/abcd/Photos/Nested", TestContext.Current.CancellationToken));
        Assert.Equal("GetHostPaths", portal.LastMethod);
        Assert.Equal(new[] { "abcd" }, portal.RequestedIds);
    }

    [LinuxFact]
    public async Task ResolveHostPathAsync_OlderOrDeniedPortalKeepsAccessPathFallback()
    {
        await using var portal = await TestDocumentsPortal.StartAsync();
        portal.DenyRequest = true;
        await using var session = new DBusSession(portal.Address);
        var client = new DocumentPortalClient(session, NullLogger<DocumentPortalClient>.Instance, _ => null);
        Assert.Null(await client.ResolveHostPathAsync("/run/user/1000/doc/abcd/Photos", TestContext.Current.CancellationToken));
    }

    [LinuxFact]
    public async Task ResolveHostPathAsync_StalledPortalReturnsWithoutBlockingShutdown()
    {
        await using var portal = await TestDocumentsPortal.StartAsync();
        portal.IgnoreRequest = true;
        await using var session = new DBusSession(portal.Address);
        var client = new DocumentPortalClient(session, NullLogger<DocumentPortalClient>.Instance, _ => null)
        {
            ResponseTimeout = TimeSpan.FromMilliseconds(100),
        };
        Assert.Null(await client.ResolveHostPathAsync("/run/user/1000/doc/abcd/Photos", TestContext.Current.CancellationToken)
            .WaitAsync(TimeSpan.FromSeconds(3), TestContext.Current.CancellationToken));
    }

    private sealed class TestDocumentsPortal(Process bus, DBusConnection connection, string address)
        : IAsyncDisposable, IPathMethodHandler
    {
        public string Address { get; } = address;
        public string Path => "/org/freedesktop/portal/documents";
        public bool HandlesChildPaths => false;
        public string? LastMethod { get; private set; }
        public string[]? RequestedIds { get; private set; }
        public bool DenyRequest { get; set; }
        public bool IgnoreRequest { get; set; }

        public static async Task<TestDocumentsPortal> StartAsync()
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
                var address = await bus.StandardOutput.ReadLineAsync(TestContext.Current.CancellationToken)
                    .AsTask().WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
                connection = new DBusConnection(address!);
                await connection.ConnectAsync();
                await connection.RequestNameAsync("org.freedesktop.portal.Documents");
                var portal = new TestDocumentsPortal(bus, connection, address!);
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
            LastMethod = context.Request.MemberAsString;
            if (IgnoreRequest) return ValueTask.CompletedTask;
            if (DenyRequest || LastMethod != "GetHostPaths")
            {
                context.ReplyError("org.freedesktop.DBus.Error.UnknownMethod", "Synthetic unavailable method");
                return ValueTask.CompletedTask;
            }
            RequestedIds = context.Request.GetBodyReader().ReadArrayOfString();
            var reply = context.CreateReplyWriter("a{say}");
            var entries = reply.WriteDictionaryStart();
            reply.WriteStructureStart();
            reply.WriteString("unrelated");
            reply.WriteArray(Encoding.UTF8.GetBytes("/home/example/Other\0"));
            reply.WriteStructureStart();
            reply.WriteString("abcd");
            reply.WriteArray(Encoding.UTF8.GetBytes("/home/example/Photos\0"));
            reply.WriteDictionaryEnd(entries);
            context.Reply(reply.CreateMessage());
            return ValueTask.CompletedTask;
        }

        public async ValueTask DisposeAsync()
        {
            connection.Dispose();
            if (!bus.HasExited) bus.Kill();
            await bus.WaitForExitAsync(TestContext.Current.CancellationToken);
            bus.Dispose();
        }
    }
}
