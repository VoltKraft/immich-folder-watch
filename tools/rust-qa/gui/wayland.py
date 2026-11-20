"""Observe commits to the application's xdg_toplevel from the private Mutter server."""

import os
from pathlib import Path
import re
import subprocess
import time

from session import checked_start, check_alive, stop, wait_for


class WaylandObserver:
    def __init__(self, stack, capture=False):
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        self.log = Path("/qa/mutter.log")
        self.events = []
        self.surface = {}
        self.toplevels = {}
        self.title = {}
        self.attached = {}
        self.mapped = set()
        self.focused_surface = None
        self.clipboard_serial = None
        env = dict(os.environ, WAYLAND_DEBUG="server", GSETTINGS_BACKEND="memory",
                   DBUS_SYSTEM_BUS_ADDRESS=os.environ["DBUS_SESSION_BUS_ADDRESS"])
        if capture:
            pipe_log = Path("/qa/pipewire.log")
            pipe = checked_start(stack, ["pipewire"], pipe_log)
            wait_for(lambda: check_alive(pipe, pipe_log) or Path("/tmp/runtime/pipewire-0").is_socket(),
                     5, "Private PipeWire server did not create its socket")
        self.mutter = subprocess.Popen(["mutter", "--wayland", "--headless", "--no-x11",
                                      "--virtual-monitor=1280x900", "--wayland-display=ifw-test"],
                                      env=env, stdout=stack.enter_context(self.log.open("w")),
                                      stderr=subprocess.STDOUT)
        stack.callback(stop, self.mutter)
        wait_for(lambda: check_alive(self.mutter, self.log) or Path("/tmp/runtime/ifw-test").is_socket(),
                 10, "Private Wayland compositor did not start")
        self.trace = stack.enter_context(self.log.open())
        os.environ.pop("DISPLAY")
        os.environ["WAYLAND_DISPLAY"] = "ifw-test"
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.flags = Gio.DBusCallFlags.NONE
        self.variant = GLib.Variant
        self.service = "org.gnome.Mutter.RemoteDesktop"
        wait_for(lambda: check_alive(self.mutter, self.log) or self.bus.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
            self.variant("(s)", (self.service,)), None, self.flags, 1500, None).unpack()[0],
            5, "Private Mutter did not acquire its remote desktop bus name")
        self.session = self.call("/org/gnome/Mutter/RemoteDesktop", self.service, "CreateSession")[0]
        self.call(self.session, self.service + ".Session", "Start")
        # Mutter adds the virtual keyboard to the seat when it first receives input.
        self.key(0xffe1, True)
        self.key(0xffe1, False)
        if capture:
            self.capture(stack, Gio, GLib)

    def capture(self, stack, gio, glib):
        service = "org.gnome.Mutter.ScreenCast"
        config = "org.gnome.Mutter.DisplayConfig"
        state = self.bus.call_sync(config, "/org/gnome/Mutter/DisplayConfig", config, "GetCurrentState",
                                   None, None, self.flags, 4000, None).unpack()
        connector = state[1][0][0][0]
        def call(path, interface, method, value=None):
            return self.bus.call_sync(service, path, interface, method, value, None,
                                      self.flags, 4000, None).unpack()
        session, = call("/org/gnome/Mutter/ScreenCast", service, "CreateSession", self.variant("(a{sv})", ({},)))
        stream, = call(session, service + ".Session", "RecordMonitor", self.variant("(sa{sv})", (connector, {})))
        nodes = []
        subscription = self.bus.signal_subscribe(service, service + ".Stream", "PipeWireStreamAdded",
            stream, None, gio.DBusSignalFlags.NONE, lambda *args: nodes.append(args[5].unpack()[0]))
        stack.callback(self.bus.signal_unsubscribe, subscription)
        call(session, service + ".Session", "Start")
        def stream_ready():
            context = glib.MainContext.default()
            while context.pending():
                context.iteration(False)
            return nodes
        wait_for(stream_ready, 6, "No PipeWire stream for the virtual monitor")
        self.capture_log = Path("/qa/capture.log")
        self.consumer = checked_start(stack, ["gst-launch-1.0", "-q", "pipewiresrc", f"path={nodes[0]}",
                                             "!", "fakesink", "sync=false"], self.capture_log)

    def call(self, obj, interface, method, args=None):
        return self.bus.call_sync(self.service, obj, interface, method, args, None,
                                  self.flags, 4000, None).unpack()

    def key(self, key, down):
        self.call(self.session, self.service + ".Session", "NotifyKeyboardKeysym",
                  self.variant("(ub)", (key, down)))

    def close(self):
        self.focus_for_input()
        self.key(0xffe9, True)  # Alt_L
        self.key(0xffc1, True)  # F4
        self.key(0xffc1, False)
        self.key(0xffe9, False)
        return "compositor Alt+F4"

    def focus_for_input(self):
        wait_for(lambda: self.poll() and self.focused_surface in self.mapped,
                 3, "Private compositor did not give keyboard focus to the mapped surface")

    def clipboard_owner(self):
        self.poll()
        return self.clipboard_serial

    def transition(self, mapped, surface):
        if mapped != (surface in self.mapped):
            if mapped:
                self.mapped.add(surface)
            else:
                self.mapped.remove(surface)
            self.events.append({"time": time.monotonic(), "event": "map" if mapped else "unmap", "surface": surface})

    def poll(self):
        check_alive(self.mutter, self.log)
        for line in self.trace:
            # libwayland used @ before version 1.24. Match both debug spellings.
            line = line.replace("@", "#")
            if match := re.search(r"get_xdg_surface\(new id xdg_surface#(\d+), wl_surface#(\d+)\)", line):
                self.surface[match[1]] = match[2]
            elif match := re.search(r"xdg_surface#(\d+)\.get_toplevel\(new id xdg_toplevel#(\d+)\)", line):
                self.toplevels[match[2]] = self.surface[match[1]]
            elif match := re.search(r'xdg_toplevel#(\d+)\.set_title\("Desktop input probe"\)', line):
                self.title[self.toplevels[match[1]]] = match[1]
            elif match := re.search(r"xdg_toplevel#(\d+)\.close\(", line):
                self.events.append({"time": time.monotonic(), "event": "compositor-close", "toplevel": match[1]})
            elif match := re.search(r"wl_keyboard#\d+\.enter\(\d+, wl_surface#(\d+)", line):
                self.focused_surface = match[1]
            elif match := re.search(r"wl_keyboard#\d+\.leave\(\d+, wl_surface#(\d+)", line):
                if self.focused_surface == match[1]:
                    self.focused_surface = None
            elif match := re.search(r"wl_data_device#\d+\.set_selection\(wl_data_source#\d+, (\d+)\)", line):
                self.clipboard_serial = match[1]
            elif match := re.search(r"wl_surface#(\d+)\.attach\(([^,]+),", line):
                if match[1] in self.title:
                    self.attached[match[1]] = match[2].startswith("wl_buffer#")
            elif match := re.search(r"wl_surface#(\d+)\.commit\(", line):
                if match[1] in self.attached:
                    self.transition(self.attached.pop(match[1]), match[1])
            elif match := re.search(r"wl_surface#(\d+)\.destroy\(", line):
                self.transition(False, match[1])
                self.title.pop(match[1], None)
                self.attached.pop(match[1], None)
        return bool(self.mapped)
