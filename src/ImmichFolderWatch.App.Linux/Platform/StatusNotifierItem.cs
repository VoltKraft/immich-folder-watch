using Tmds.DBus.Protocol;

namespace ImmichFolderWatch.App.Linux.Platform;

/// <summary>
/// Exports an SNI item and its DBusMenu under the application's own bus namespace.
/// Avalonia's built-in exporter uses a KDE-owned name which Flatpak cannot own.
/// This connection is dedicated so disposal atomically withdraws the item and menu.
/// </summary>
internal sealed class StatusNotifierItem : IDisposable, IPathMethodHandler
{
    internal const string BusName = "io.github.voltkraft.immich-folder-watch.Tray";
    internal const string Watcher = "org.kde.StatusNotifierWatcher";
    internal const string ItemInterface = "org.kde.StatusNotifierItem";
    internal const string MenuInterface = "com.canonical.dbusmenu";
    internal const string MenuPath = "/StatusNotifierItem/Menu";
    private const string PropertiesInterface = "org.freedesktop.DBus.Properties";
    private readonly DBusConnection _connection;
    private readonly object _stateGate = new();
    private long _registrationGeneration;
    private readonly byte[] _icon;
    private readonly int _width;
    private readonly int _height;
    private IDisposable? _watch;
    private uint _revision = 1;
    private string _title = "Immich Folder Watch";
    private string[] _labels = ["Open", "Restart", "Quit"];
    private bool _disposed;

    public StatusNotifierItem(string address, int width, int height, byte[] argbIcon)
    {
        _connection = new DBusConnection(address);
        _width = width;
        _height = height;
        _icon = argbIcon;
    }

    public string Path => "/StatusNotifierItem";
    public bool HandlesChildPaths => true;
    public bool IsRegistered { get; private set; }
    public event Action<int>? Activated;
    public event Action<bool>? AvailabilityChanged;

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        await _connection.ConnectAsync().AsTask().WaitAsync(cancellationToken).ConfigureAwait(false);
        _connection.AddMethodHandler(this);
        await _connection.RequestNameAsync(BusName).WaitAsync(cancellationToken).ConfigureAwait(false);
        _watch = await _connection.AddMatchAsync(new MatchRule
        {
            Type = MessageType.Signal, Sender = "org.freedesktop.DBus",
            Interface = "org.freedesktop.DBus", Member = "NameOwnerChanged", Arg0 = Watcher,
        }, static (message, _) =>
        {
            var reader = message.GetBodyReader();
            _ = reader.ReadString();
            _ = reader.ReadString();
            return reader.ReadString();
        }, (error, owner, _, _) =>
        {
            if (_disposed) return;
            if (error is not null || string.IsNullOrEmpty(owner)) InvalidateRegistration();
            else _ = RegisterAsync(CancellationToken.None);
        }, flags: ObserverFlags.None, emitOnCapturedContext: false).ConfigureAwait(false);
        await RegisterAsync(cancellationToken).ConfigureAwait(false);
    }

    private async Task RegisterAsync(CancellationToken cancellationToken)
    {
        long generation;
        lock (_stateGate)
        {
            if (_disposed) return;
            generation = ++_registrationGeneration;
        }
        try
        {
            var writer = _connection.GetMessageWriter();
            writer.WriteMethodCallHeader(destination: Watcher, path: "/StatusNotifierWatcher",
                @interface: Watcher, member: "RegisterStatusNotifierItem", signature: "s");
            writer.WriteString(BusName);
            await _connection.CallMethodAsync(writer.CreateMessage()).WaitAsync(TimeSpan.FromSeconds(3), cancellationToken)
                .ConfigureAwait(false);
            SetAvailable(true, generation);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception) { SetAvailable(false, generation); }
    }

    private void InvalidateRegistration()
    {
        lock (_stateGate)
        {
            if (_disposed) return;
            ++_registrationGeneration;
            IsRegistered = false;
            AvailabilityChanged?.Invoke(false);
        }
    }

    private void SetAvailable(bool available, long generation)
    {
        lock (_stateGate)
        {
            // A former watcher can reply after relinquishing its name. Its reply
            // must not overwrite a loss notification or a replacement's state.
            if (_disposed || generation != _registrationGeneration) return;
            IsRegistered = available;
            AvailabilityChanged?.Invoke(available);
        }
    }

    public void Update(string title, string open, string restart, string quit)
    {
        if (_disposed) return;
        _title = title;
        _labels = [open, restart, quit];
        unchecked { _revision++; }
        if (!IsRegistered) return;
        Signal(Path, ItemInterface, "NewTitle");
        Signal(Path, ItemInterface, "NewToolTip");
        var writer = _connection.GetMessageWriter();
        writer.WriteSignalHeader(path: MenuPath, @interface: MenuInterface, member: "LayoutUpdated", signature: "ui");
        writer.WriteUInt32(_revision);
        writer.WriteInt32(0);
        _connection.TrySendMessage(writer.CreateMessage());
    }

    private void Signal(string path, string iface, string member)
    {
        var writer = _connection.GetMessageWriter();
        writer.WriteSignalHeader(path: path, @interface: iface, member: member);
        _connection.TrySendMessage(writer.CreateMessage());
    }

    public ValueTask HandleMethodAsync(MethodContext context)
    {
        var request = context.Request;
        var menu = request.PathAsString == MenuPath;
        var member = request.MemberAsString;
        if (request.InterfaceAsString == PropertiesInterface)
        {
            var reader = request.GetBodyReader();
            var iface = reader.ReadString();
            if (iface != (menu ? MenuInterface : ItemInterface))
                context.ReplyError("org.freedesktop.DBus.Error.InvalidArgs", "Unknown interface");
            else if (member == "GetAll")
            {
                var reply = context.CreateReplyWriter("a{sv}");
                reply.WriteDictionary(Properties(menu));
                context.Reply(reply.CreateMessage());
            }
            else if (member == "Get" && Properties(menu).TryGetValue(reader.ReadString(), out var value))
            {
                var reply = context.CreateReplyWriter("v");
                reply.WriteVariant(value);
                context.Reply(reply.CreateMessage());
            }
            else context.ReplyError("org.freedesktop.DBus.Error.UnknownProperty", "Unknown or read-only property");
        }
        else if (request.InterfaceAsString == "org.freedesktop.DBus.Introspectable" && member == "Introspect")
        {
            var reply = context.CreateReplyWriter("s");
            reply.WriteString(menu ? MenuXml : ItemXml);
            context.Reply(reply.CreateMessage());
        }
        else if (!menu && request.InterfaceAsString == ItemInterface && member is "Activate" or "SecondaryActivate" or "ContextMenu" or "Scroll")
        {
            EmptyReply(context);
            if (member is "Activate" or "SecondaryActivate") Activated?.Invoke(1);
        }
        else if (menu && request.InterfaceAsString == MenuInterface) HandleMenu(context);
        else context.ReplyUnknownMethodError();
        return ValueTask.CompletedTask;
    }

    private Dictionary<string, VariantValue> Properties(bool menu)
    {
        if (menu) return new() { ["Version"] = 3u, ["TextDirection"] = "ltr", ["Status"] = "normal", ["IconThemePath"] = VariantValue.Array(System.Array.Empty<string>()) };
        var pixmap = new Tmds.DBus.Protocol.Array<Struct<int, int, Tmds.DBus.Protocol.Array<byte>>>
        {
            new(_width, _height, new Tmds.DBus.Protocol.Array<byte>(_icon)),
        };
        return new()
        {
            ["Category"] = "ApplicationStatus", ["Id"] = "io.github.voltkraft.immich-folder-watch",
            ["Title"] = _title, ["Status"] = "Active", ["WindowId"] = 0u,
            ["IconName"] = "io.github.voltkraft.immich-folder-watch", ["IconPixmap"] = pixmap,
            ["OverlayIconName"] = "", ["AttentionIconName"] = "", ["AttentionMovieName"] = "",
            ["OverlayIconPixmap"] = new Tmds.DBus.Protocol.Array<Struct<int, int, Tmds.DBus.Protocol.Array<byte>>>(),
            ["AttentionIconPixmap"] = new Tmds.DBus.Protocol.Array<Struct<int, int, Tmds.DBus.Protocol.Array<byte>>>(),
            ["ToolTip"] = VariantValue.Struct("", pixmap, "Immich Folder Watch", _title),
            ["ItemIsMenu"] = false, ["Menu"] = new ObjectPath(MenuPath),
        };
    }

    private Dictionary<string, VariantValue> MenuProperties(int id) => id switch
    {
        0 => new() { ["children-display"] = "submenu" },
        1 or 2 or 3 => new() { ["label"] = _labels[id - 1], ["enabled"] = true, ["visible"] = true },
        _ => new(),
    };

    private void HandleMenu(MethodContext context)
    {
        var reader = context.Request.GetBodyReader();
        switch (context.Request.MemberAsString)
        {
            case "GetLayout":
            {
                var id = reader.ReadInt32();
                var depth = reader.ReadInt32();
                var properties = reader.ReadArrayOfString();
                var reply = context.CreateReplyWriter("u(ia{sv}av)");
                reply.WriteUInt32(_revision);
                WriteLayout(ref reply, id, depth, properties);
                context.Reply(reply.CreateMessage());
                break;
            }
            case "GetGroupProperties":
            {
                var ids = reader.ReadArrayOfInt32();
                var properties = reader.ReadArrayOfString();
                var reply = context.CreateReplyWriter("a(ia{sv})");
                var array = reply.WriteArrayStart(DBusType.Struct);
                foreach (var id in ids.Length == 0 ? new[] { 0, 1, 2, 3 } : ids)
                {
                    reply.WriteStructureStart();
                    reply.WriteInt32(id);
                    reply.WriteDictionary(FilteredProperties(id, properties));
                }
                reply.WriteArrayEnd(array);
                context.Reply(reply.CreateMessage());
                break;
            }
            case "GetProperty":
            {
                var id = reader.ReadInt32();
                var name = reader.ReadString();
                if (!MenuProperties(id).TryGetValue(name, out var value)) { context.ReplyError("com.canonical.dbusmenu.Error.InvalidProperty", "Unknown property"); break; }
                var reply = context.CreateReplyWriter("v"); reply.WriteVariant(value); context.Reply(reply.CreateMessage());
                break;
            }
            case "Event":
            {
                var id = reader.ReadInt32(); var kind = reader.ReadString();
                _ = reader.ReadVariantValue(); _ = reader.ReadUInt32();
                EmptyReply(context);
                if (kind == "clicked" && id is >= 1 and <= 3) Activated?.Invoke(id);
                break;
            }
            case "EventGroup":
            {
                var events = reader.ReadArrayStart(DBusType.Struct);
                var clicked = new List<int>();
                while (reader.HasNext(events))
                {
                    reader.AlignStruct();
                    var id = reader.ReadInt32(); var kind = reader.ReadString();
                    _ = reader.ReadVariantValue(); _ = reader.ReadUInt32();
                    if (kind == "clicked" && id is >= 1 and <= 3) clicked.Add(id);
                }
                var reply = context.CreateReplyWriter("ai"); reply.WriteArray(System.Array.Empty<int>()); context.Reply(reply.CreateMessage());
                foreach (var id in clicked) Activated?.Invoke(id);
                break;
            }
            case "AboutToShow":
            {
                var reply = context.CreateReplyWriter("b"); reply.WriteBool(false); context.Reply(reply.CreateMessage()); break;
            }
            case "AboutToShowGroup":
            {
                var reply = context.CreateReplyWriter("aiai"); reply.WriteArray(System.Array.Empty<int>()); reply.WriteArray(System.Array.Empty<int>()); context.Reply(reply.CreateMessage()); break;
            }
            default: context.ReplyUnknownMethodError(); break;
        }
    }

    private Dictionary<string, VariantValue> FilteredProperties(int id, string[] properties) =>
        MenuProperties(id).Where(pair => properties.Length == 0 || properties.Contains(pair.Key)).ToDictionary();

    private void WriteLayout(ref MessageWriter writer, int id, int depth, string[] properties)
    {
        writer.WriteStructureStart();
        writer.WriteInt32(id);
        writer.WriteDictionary(FilteredProperties(id, properties));
        var children = writer.WriteArrayStart(DBusType.Variant);
        if (id == 0 && depth != 0)
        {
            for (var child = 1; child <= 3; child++)
            {
                writer.WriteSignature("(ia{sv}av)");
                WriteLayout(ref writer, child, 0, properties);
            }
        }
        writer.WriteArrayEnd(children);
    }

    private static void EmptyReply(MethodContext context)
    {
        var reply = context.CreateReplyWriter(null); context.Reply(reply.CreateMessage());
    }

    public void Dispose()
    {
        lock (_stateGate)
        {
            if (_disposed) return;
            _disposed = true;
            ++_registrationGeneration;
            IsRegistered = false;
        }
        _watch?.Dispose();
        _connection.Dispose();
    }

    private const string ItemXml = """
        <node><interface name="org.kde.StatusNotifierItem">
        <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
        <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
        <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
        <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
        <property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
        <property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
        <property name="WindowId" type="u" access="read"/><property name="IconName" type="s" access="read"/>
        <property name="IconPixmap" type="a(iiay)" access="read"/><property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
        <property name="Menu" type="o" access="read"/><property name="ItemIsMenu" type="b" access="read"/>
        <signal name="NewTitle"/><signal name="NewToolTip"/><signal name="NewIcon"/>
        </interface><node name="Menu"/></node>
        """;
    private const string MenuXml = """
        <node><interface name="com.canonical.dbusmenu">
        <method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
        <method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
        <method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
        <method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
        <method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
        <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
        <method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
        <property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/>
        <property name="Status" type="s" access="read"/><property name="IconThemePath" type="as" access="read"/>
        <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
        </interface></node>
        """;
}
