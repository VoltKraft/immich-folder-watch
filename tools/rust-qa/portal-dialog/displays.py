"""Observe native dialog parenting at independent X11 and Wayland clients and inject test keys."""

import ctypes as c
import os
from pathlib import Path
import re
import subprocess
import time
from session import checked_start, check_alive, stop, wait_for
from x11 import bind, WindowAttributes
TITLE = 'Select a synthetic watch folder'
PARENT = 'Synthetic native portal parent'


class X11:

    def __init__(self, display):
        self.x = display
        lib = c.CDLL('libX11.so.6')
        self.focus = bind(lib, 'XSetInputFocus', c.c_int, c.c_void_p, c.c_ulong, c.c_int, c.c_ulong)
        self.to_code = bind(lib, 'XKeysymToKeycode', c.c_uint, c.c_void_p, c.c_ulong)
        self.fake_key = bind(c.CDLL('libXtst.so.6'), 'XTestFakeKeyEvent', c.c_int, c.c_void_p, c.c_uint, c.c_int,
            c.c_ulong)
        self.dialog = None

    def windows(self):
        x = self.x
        root, parent, children = (c.c_ulong(), c.c_ulong(), c.POINTER(c.c_ulong)())
        count = c.c_uint()
        if not x.query(x.display, x.root, c.byref(root), c.byref(parent), c.byref(children), c.byref(count)):
            raise RuntimeError('Cannot inspect private X11 toplevel windows')
        try:
            found = {}
            for i in range(count.value):
                window = children[i]
                attrs = WindowAttributes()
                if x.attributes(x.display, window, c.byref(attrs)) and attrs.map_state == 2 and (attrs.width > 150):
                    props = subprocess.run(['xprop', '-id', str(window), '_NET_WM_NAME', 'WM_TRANSIENT_FOR'],
                        text=True, capture_output=True).stdout
                    found[window] = props
            return found
        finally:
            if children:
                x.free(children)

    def observe(self, identifier):
        if not identifier.startswith('x11:'):
            raise RuntimeError('Missing actual X11 parent')
        expected = int(identifier[4:], 16)
        windows = self.windows()
        if expected not in windows or PARENT not in windows[expected]:
            return None
        for window, props in windows.items():
            if TITLE not in props:
                continue
            self.dialog = window
            match = re.search('WM_TRANSIENT_FOR.*?\\b(0x[0-9a-fA-F]+)', props)
            if match is None or int(match[1], 16) != expected:
                return None
            return {'parent': hex(expected), 'dialog': hex(window), 'xproperties': props.splitlines()}
        return None

    def key(self, keysym, down):
        if not self.dialog:
            raise RuntimeError('No verified X11 dialog')
        self.focus(self.x.display, self.dialog, 2, 0)
        code = self.to_code(self.x.display, keysym)
        if not code or not self.fake_key(self.x.display, code, int(down), 0):
            raise RuntimeError('XTEST key failed')
        self.x.sync(self.x.display, 0)


class Wayland:

    def __init__(self, stack, bus, desktop_shell=False):
        from gi.repository import Gio, GLib
        self.gio, self.glib, self.bus = (Gio, GLib, bus)
        self.log = Path('/qa/mutter.log')
        env = dict(os.environ, WAYLAND_DEBUG='server', GSETTINGS_BACKEND='memory',
            DBUS_SYSTEM_BUS_ADDRESS=os.environ['DBUS_SESSION_BUS_ADDRESS'])
        compositor = 'gnome-shell' if desktop_shell else 'mutter'
        p = subprocess.Popen([compositor, '--wayland', '--no-x11', '--headless', '--virtual-monitor=1280x900',
            '--wayland-display=ifw-dialog'], env=env, stdout=stack.enter_context(self.log.open('w')),
            stderr=subprocess.STDOUT)
        stack.callback(stop, p)
        socket = Path(os.environ['XDG_RUNTIME_DIR']) / 'ifw-dialog'
        wait_for(lambda: check_alive(p, self.log) or socket.is_socket(), 8,
            'No independent headless Wayland compositor')
        os.environ.pop('DISPLAY', None)
        os.environ['WAYLAND_DISPLAY'] = 'ifw-dialog'
        self.service = 'org.gnome.Mutter.RemoteDesktop'

        def session():
            try:
                return self.call('/org/gnome/Mutter/RemoteDesktop', self.service, 'CreateSession')[0]
            except GLib.Error:
                return None
        self.session = wait_for(session, 6, 'Mutter remote keyboard unavailable')
        self.call(self.session, self.service + '.Session', 'Start')
        self.key(65505, True)
        self.key(65505, False)

    def call(self, path, iface, method, args=None):
        return self.bus.call_sync(self.service, path, iface, method, args, None, self.gio.DBusCallFlags.NONE,
            2000, None).unpack()

    def key(self, keysym, down):
        self.call(self.session, self.service + '.Session', 'NotifyKeyboardKeysym',
            self.glib.Variant('(ub)', (keysym, down)))

    def observe(self, identifier):
        if not identifier.startswith('wayland:'):
            raise RuntimeError('Missing exported Wayland parent')
        token = re.escape(identifier.removeprefix('wayland:'))

        def trace(path):
            return re.sub('\\b((?:wl|xdg|zxdg)_[a-z0-9_]+)@(?=\\d+)', '\\1#', path.read_text())
        server = trace(self.log)
        backend = trace(Path('/qa/gtk.log'))
        exported = re.search('zxdg_exported_v2#(\\d+)\\.handle\\("' + token + '"\\)', server)
        imported = re.search('zxdg_importer_v[12]#\\d+\\.import(?:_toplevel)?\\(new id (zxdg_imported_v[12]#\\d+), "' + token + '"\\)', backend)
        if not exported or not imported:
            return None
        linked = re.search(re.escape(imported[1]) + '\\.set_parent_of\\(wl_surface#(\\d+)\\)',
            backend[imported.end():])
        if not linked:
            return None
        surface = re.escape(linked[1])
        xdg = re.findall('get_xdg_surface\\(new id xdg_surface#(\\d+), wl_surface#' + surface + '\\)', backend)
        if not xdg:
            return None
        tops = re.findall('xdg_surface#' + xdg[-1] + '\\.get_toplevel\\(new id xdg_toplevel#(\\d+)\\)', backend)
        if not tops or not re.search('xdg_toplevel#' + tops[-1] + '\\.set_title\\("' + re.escape(TITLE) + '"\\)',
            backend):
            return None
        if not re.search('wl_surface#' + surface + '\\.attach\\(wl_buffer#', backend):
            return None
        if not re.search('wl_keyboard#\\d+\\.enter\\(\\d+, wl_surface#' + surface + ',', backend[imported.end():]):
            return None
        return {'parent': identifier, 'server_export': exported[0], 'backend_import': imported[0],
            'backend_parent': linked[0], 'dialog_surface': linked[1], 'title': TITLE}


def stroke(display, sym):
    display.key(sym, True)
    display.key(sym, False)


def input_action(display, action):
    if action == 'cancel':
        display.key(65513, True)
        stroke(display, ord('c'))
        display.key(65513, False)
        return
    time.sleep(0.22)
    display.key(65513, True)
    stroke(display, ord('u'))
    display.key(65513, False)
