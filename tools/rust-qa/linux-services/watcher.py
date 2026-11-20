"""Synthetic SNI watcher on the real private session bus, including late and failed replies."""

import os
import sys
from gi.repository import Gio, GLib


WATCHER = "org.kde.StatusNotifierWatcher"
APP = "org.example.IfwServices"
PEER = "org.example.WatcherControl"
PATH = "/StatusNotifierWatcher"
BUS = "org.freedesktop.DBus"
MODE = sys.argv[1]
if MODE not in {"accept", "delay", "refuse"} or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus":
    raise RuntimeError("Use a private assessment bus and a supported synthetic watcher mode")
bus = Gio.bus_get_sync(Gio.BusType.SESSION)
desc = Gio.DBusNodeInfo.new_for_xml(f"""<node><interface name="{WATCHER}">
<method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method></interface>
<interface name="{PEER}"><method name="Activate"/><method name="Release"/><method name="Acknowledge"/>
</interface></node>""")
states = {"pending": [], "registered": set()}


def call(destination, path, interface, method, args=None):
    return bus.call_sync(destination, path, interface, method, args, None, Gio.DBusCallFlags.NONE, 2000, None).unpack()


def received(connection, sender, path, interface, method, arguments, invocation):
    if interface == WATCHER:
        service, = arguments.unpack()
        owner, = call(BUS, "/org/freedesktop/DBus", BUS, "GetNameOwner", GLib.Variant("(s)", (service,)))
        if owner != sender:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.AccessDenied", "Item name belongs to another sender")
            return
        print("REGISTER", service, sender, MODE, flush=True)
        if MODE == "refuse":
            invocation.return_dbus_error("org.freedesktop.DBus.Error.AccessDenied", "Synthetic panel refused the item")
            return
        if MODE == "delay" and service == APP:
            states["pending"].append(invocation)
            return
        states["registered"].add(service)
    elif method == "Activate":
        if APP not in states["registered"]:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.Failed", "No registered item")
            return
        call(APP, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "Activate", GLib.Variant("(ii)", (0, 0)))
    elif method == "Release":
        call(BUS, "/org/freedesktop/DBus", BUS, "ReleaseName", GLib.Variant("(s)", (WATCHER,)))
    elif method == "Acknowledge":
        for waiting in states["pending"]:
            waiting.return_value(None)
        print("LATE_REPLIES", len(states["pending"]), flush=True)
        states["pending"].clear()
    invocation.return_value(None)


for interface in desc.interfaces:
    bus.register_object(PATH, interface, received, None, None)
code, = call(BUS, "/org/freedesktop/DBus", BUS, "RequestName", GLib.Variant("(su)", (WATCHER, 4)))
if code != 1:
    raise RuntimeError("Private watcher name already exists")
print("READY", bus.get_unique_name(), flush=True)
GLib.MainLoop().run()
