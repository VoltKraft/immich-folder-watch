"""A synthetic notification server to observe real GTK backend delivery over the private bus."""

import json
import os
from pathlib import Path
from gi.repository import Gio, GLib
name = 'org.freedesktop.Notifications'
dbus = 'org.freedesktop.DBus'
if os.environ.get('DBUS_SESSION_BUS_ADDRESS') != 'unix:path=/tmp/session-bus':
    raise RuntimeError('Expected private notification assessment bus')
bus = Gio.bus_get_sync(Gio.BusType.SESSION)
events = []
doc = Gio.DBusNodeInfo.new_for_xml(f'<node><interface name="{name}">\n<method name="GetCapabilities"><arg type="as" direction="out"/></method>\n<method name="GetServerInformation"><arg type="s" direction="out"/><arg type="s" direction="out"/><arg type="s" direction="out"/><arg type="s" direction="out"/></method>\n<method name="Notify"><arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="as" direction="in"/><arg type="a{{sv}}" direction="in"/><arg type="i" direction="in"/><arg type="u" direction="out"/></method>\n<method name="CloseNotification"><arg type="u" direction="in"/></method></interface></node>')


def replied(connection, sender, path, interface, method, args, invocation):
    if method == 'GetCapabilities':
        result = GLib.Variant('(as)', (['body'],))
    elif method == 'GetServerInformation':
        result = GLib.Variant('(ssss)', ('Synthetic receiver', 'Assessment', '1.0', '1.2'))
    else:
        if method == 'Notify':
            app, _, _, title, body, _, _, _ = args.unpack()
            events.append({'method': method, 'sender': sender, 'app': app, 'title': title, 'body': body})
            result = GLib.Variant('(u)', (73,))
        elif method == 'CloseNotification':
            identifier, = args.unpack()
            events.append({'method': method, 'sender': sender, 'id': identifier})
            result = None
        else:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.UnknownMethod', 'Unknown fixture method')
            return
        receipt = Path('/qa/notification-events.json')
        staged = receipt.with_suffix('.writing')
        staged.write_text(json.dumps(events, indent=2) + '\n')
        staged.replace(receipt)
    invocation.return_value(result)
bus.register_object('/org/freedesktop/Notifications', doc.interfaces[0], replied, None, None)
code, = bus.call_sync(dbus, '/org/freedesktop/DBus', dbus, 'RequestName', GLib.Variant('(su)', (name, 4)), None,
    Gio.DBusCallFlags.NONE, 2000, None).unpack()
if code != 1:
    raise RuntimeError('Notification name already owned')
print('READY', flush=True)
GLib.MainLoop().run()
