"""A protocol peer on the isolated bus. It records SNI registration and exports no UI."""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


WATCHER = "org.kde.StatusNotifierWatcher"
description = Gio.DBusNodeInfo.new_for_xml(f"""
<node><interface name="{WATCHER}">
  <method name="RegisterStatusNotifierItem"><arg name="service" type="s" direction="in"/></method>
</interface></node>""")


def register(connection, sender, path, interface, method, arguments, invocation):
    service, = arguments.unpack()
    print("REGISTERED", service, sender, flush=True)
    invocation.return_value(None)


def acquired(connection, name):
    print("WATCHER_READY", flush=True)


loop = GLib.MainLoop()
# A client can register as soon as NameOwnerChanged is delivered on the bus.
connection = Gio.bus_get_sync(Gio.BusType.SESSION)
connection.register_object("/StatusNotifierWatcher", description.interfaces[0], register, None, None)
Gio.bus_own_name_on_connection(connection, WATCHER, Gio.BusNameOwnerFlags.NONE, acquired, lambda *_: loop.quit())
loop.run()
