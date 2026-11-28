"""Call the watcher's real registration method on the first owner-change signal of a private bus."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from gi.repository import Gio, GLib

WATCHER = 'org.kde.StatusNotifierWatcher'
DBUS = 'org.freedesktop.DBus'
DBUS_PATH = '/org/freedesktop/DBus'


def check(address):
    flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
    bus = Gio.DBusConnection.new_for_address_sync(address, flags, None, None)
    observations = []
    def call(owner, path, interface, method, arguments):
        return bus.call_sync(owner, path, interface, method, arguments, None, Gio.DBusCallFlags.NO_AUTO_START, 2000, None)
    def appeared(connection, sender, path, interface, signal, arguments):
        _, _, new = arguments.unpack()
        if new:
            try:
                call(new, '/StatusNotifierWatcher', WATCHER, 'RegisterStatusNotifierItem', GLib.Variant('(s)', ('test-item',)))
                pid, = call(DBUS, DBUS_PATH, DBUS, 'GetConnectionUnixProcessID', GLib.Variant('(s)', (new,))).unpack()
                observations.append({'owner': new, 'pid': pid})
            except GLib.Error as error:
                observations.append({'owner': new, 'error': str(error)})

    bus.signal_subscribe(DBUS, DBUS, 'NameOwnerChanged', DBUS_PATH, WATCHER, Gio.DBusSignalFlags.NONE, appeared)
    call(DBUS, DBUS_PATH, DBUS, 'GetId', None)  # The bus has processed this connection's match rule.
    context = GLib.MainContext.default()
    for index in range(16):
        watcher = subprocess.Popen([sys.executable, '-B', Path(__file__).with_name('watcher.py')], text=True,
                                   stdout=subprocess.PIPE, env={**os.environ, 'DBUS_SESSION_BUS_ADDRESS': address})
        try:
            deadline = time.monotonic() + 4
            while len(observations) == index and time.monotonic() < deadline and watcher.poll() is None:
                context.iteration(False)
                time.sleep(.001)
            if len(observations) != index + 1 or observations[index].get('pid') != watcher.pid:
                raise RuntimeError(f'The new owner did not accept its first registration: {observations[index:]}')
        finally:
            watcher.terminate()
            log, _ = watcher.communicate(timeout=3)
        if 'REGISTERED test-item ' + bus.get_unique_name() not in log.splitlines():
            raise RuntimeError(f'The watcher did not receive the registration from the test client: {log}')
    if len({row['owner'] for row in observations}) != len(observations):
        raise ValueError('Expected a different owner for every watcher')
    return observations


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as folder:
        address = 'unix:path=' + folder + '/bus'
        daemon = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--address=' + address, '--print-address=1'],
                                  stdout=subprocess.PIPE, text=True)
        try:
            print(json.dumps(check(daemon.stdout.readline().strip()), indent=2))
        finally:
            daemon.terminate()
            daemon.wait(timeout=3)
