"""Exercise the installed GUI's ordinary tray menu from a peer on the private desktop bus."""

import os
import re
import sys

from gi.repository import Gio, GLib
from run import APP
from session import check_alive, checked_start, stop, wait_for


WATCHER = 'org.kde.StatusNotifierWatcher'
ITEM = 'org.kde.StatusNotifierItem'
ITEM_PATH = '/StatusNotifierItem'
MENU = 'com.canonical.dbusmenu'
MENU_PATH = ITEM_PATH + '/Menu'
DBUS = 'org.freedesktop.DBus'
PROPERTIES = DBUS + '.Properties'


def monitor(stack, out):
    path = out / 'menu-bus.log'
    process = checked_start(stack, ['stdbuf', '-oL', 'dbus-monitor', '--session',
        f"type='signal',interface='{DBUS}',member='NameOwnerChanged',arg0='{WATCHER}'",
        f"type='method_call',interface='{WATCHER}',member='RegisterStatusNotifierItem'",
        f"type='method_call',path='{ITEM_PATH}',interface='{PROPERTIES}',member='Get'",
        f"type='method_call',interface='{MENU}'", "type='method_return'", "type='error'"], path)
    wait_for(lambda: check_alive(process, path) or 'member=NameLost' in path.read_text(),
             5, 'The bus monitor did not switch into monitoring mode')
    return path


def watcher_peer(bus, dbus_call, watcher):
    peer = dbus_call(bus, 'GetNameOwner', WATCHER)
    pid = dbus_call(bus, 'GetConnectionUnixProcessID', peer)
    if watcher.poll() is not None or pid != watcher.pid:
        raise RuntimeError('The running watcher does not own its bus name')
    return {'owner': peer, 'pid': pid}


def replace_watcher(stack, bus, dbus_call, original, log, primary_log, proxy, out, report, require_hidden):
    old = report['originalWatcher'] = watcher_peer(bus, dbus_call, original)
    registration = f'REGISTERED {APP} {proxy}'
    if log.read_text().splitlines().count(registration) != 1:
        raise RuntimeError('Missing original watcher receipt from the installed proxy')
    stop(original)
    def released():
        require_hidden()
        return (not dbus_call(bus, 'NameHasOwner', WATCHER)
                and f"TRAY_OWNER old={old['owner']} new=none" in primary_log.read_text().splitlines())
    wait_for(released, 8, 'The hidden GUI did not observe the watcher release')
    new_log = out / 'replacement-watcher.log'
    new = checked_start(stack, [sys.executable, '-B', '/app/watcher.py'], new_log)
    def registered():
        check_alive(new, new_log)
        require_hidden()
        return registration in new_log.read_text().splitlines()
    wait_for(registered, 8, 'The replacement watcher did not receive a fresh registration')
    peer = report['replacementWatcher'] = watcher_peer(bus, dbus_call, new)
    if old['pid'] == peer['pid'] or old['owner'] == peer['owner']:
        raise RuntimeError('Watcher replacement reused the original peer')
    confirm = f"TRAY_REGISTRATION owner={peer['owner']} confirmed={peer['owner']} available=true"
    wait_for(lambda: require_hidden() or confirm in primary_log.read_text().splitlines(),
             5, 'The GUI did not confirm the replacement watcher')


def call(bus, path, interface, method, arguments, reply_type):
    return bus.call_sync(APP, path, interface, method, arguments, GLib.VariantType.new(reply_type),
                         Gio.DBusCallFlags.NO_AUTO_START, 3000, None).unpack()


def read_layout(bus, dbus_call, report, labels=('GUI öffnen', 'Neustart', 'Beenden')):
    sender = bus.get_unique_name()
    pid = dbus_call(bus, 'GetConnectionUnixProcessID', sender)
    if pid != os.getpid():
        raise RuntimeError('The menu peer is outside the protocol observer')
    report['menuPeer'] = {'owner': sender, 'pid': pid}
    path, = call(bus, ITEM_PATH, PROPERTIES, 'Get', GLib.Variant('(ss)', (ITEM, 'Menu')), '(v)')
    if path != MENU_PATH:
        raise RuntimeError(f'Unexpected Menu object: {path}')
    revision, (root, props, rows) = call(bus, path, MENU, 'GetLayout', GLib.Variant('(iias)', (0, 1, [])),
                                         '(u(ia{sv}av))')
    entries = [(index, {'label': label, 'enabled': True, 'visible': True}, [])
               for index, label in enumerate(labels, 1)]
    if not revision or root != 0 or props.get('children-display') != 'submenu' or rows != entries:
        raise RuntimeError(f'Unexpected native menu layout: {rows}')
    report.update(menuPath=path, revision=revision, entries=rows)


def click(bus, path, item):
    call(bus, path, MENU, 'Event', GLib.Variant('(isvu)', (item, 'clicked', GLib.Variant('s', ''), 0)), '()')


def verify_trace(path, report, proxy):
    """Bind both registrations, menu requests and replies to their actual senders and wire serials."""
    messages = re.split(r'\n(?=method call |method return |signal |error )', path.read_text().strip())
    cursor = 0

    def next_match(header, body=None):
        nonlocal cursor
        for index in range(cursor, len(messages)):
            first, *rest = messages[index].splitlines()
            match = re.fullmatch(header, first)
            if match and (body is None or [line.strip() for line in rest] == body):
                cursor = index + 1
                return match
        raise ValueError(f'Missing ordered D-Bus message matching {header} {body}')

    def quote(value):
        return f'string "{value}"'

    def observed_call(sender, dest, path, api, member, body, responder):
        route = re.escape(f'sender={sender} -> destination={dest} serial=')
        method = re.escape(f' path={path}; interface={api}; member={member}')
        request = next_match(r'method call time=[\d.]+ ' + route + r'(\d+)' + method, body)
        serial = int(request[1])
        reverse = re.escape(f'sender={responder} -> destination={sender} serial=')
        next_match(r'method return time=[\d.]+ ' + reverse + rf'\d+ reply_serial={serial}')
        return serial

    old = report['originalWatcher']['owner']
    new = report['replacementWatcher']['owner']
    sender = report['menuPeer']['owner']
    register = lambda watcher: observed_call(proxy, watcher, '/StatusNotifierWatcher', WATCHER,
        'RegisterStatusNotifierItem', [quote(APP)], watcher)
    registrations = [register(old)]
    owner_changed = (r'signal time=[\d.]+ sender=org\.freedesktop\.DBus -> destination=\(null destination\) '
                     r'serial=\d+ path=/org/freedesktop/DBus; interface=org\.freedesktop\.DBus; member=NameOwnerChanged')
    for previous, current in ((old, ''), ('', new)):
        next_match(owner_changed, list(map(quote, (WATCHER, previous, current))))
    registrations.append(register(new))
    menu_property = observed_call(sender, APP, ITEM_PATH, PROPERTIES, 'Get', list(map(quote, (ITEM, 'Menu'))), proxy)
    layout = observed_call(sender, APP, MENU_PATH, MENU, 'GetLayout', ['int32 0', 'int32 1', 'array [', ']'], proxy)
    events = [observed_call(sender, APP, MENU_PATH, MENU, 'Event',
                            [f'int32 {item}', quote('clicked'), 'variant       string ""', 'uint32 0'], proxy)
              for item in (1, 3)]
    report['requestSerials'] = dict(registrations=registrations, menuProperty=menu_property,
                                    getLayout=layout, open=events[0], quit=events[1])
