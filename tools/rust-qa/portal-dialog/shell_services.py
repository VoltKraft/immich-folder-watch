"""Observe the real private GNOME Shell notification display and background portal."""

from pathlib import Path
import time
from session import checked_start, check_alive, wait_for


def screen(stack, bus):
    from gi.repository import Gio, GLib
    service = 'org.gnome.Mutter.ScreenCast'
    config = 'org.gnome.Mutter.DisplayConfig'

    def call(name, path, interface, method, args=None):
        return bus.call_sync(name, path, interface, method, args, None, Gio.DBusCallFlags.NONE, 4000, None).unpack()
    monitor = call(config, '/org/gnome/Mutter/DisplayConfig', config, 'GetCurrentState')[1][0][0][0]
    session, = call(service, '/org/gnome/Mutter/ScreenCast', service, 'CreateSession', GLib.Variant('(a{sv})', ({},)))
    stream, = call(service, session, service + '.Session', 'RecordMonitor', GLib.Variant('(sa{sv})', (monitor, {})))
    nodes = []
    watch = bus.signal_subscribe(service, service + '.Stream', 'PipeWireStreamAdded', stream, None,
        Gio.DBusSignalFlags.NONE, lambda *args: nodes.append(args[5].unpack()[0]))
    stack.callback(bus.signal_unsubscribe, watch)
    call(service, session, service + '.Session', 'Start')

    def ready():
        main = GLib.MainContext.default()
        while main.pending():
            main.iteration(False)
        return nodes
    wait_for(ready, 6, 'No GNOME Shell display stream')
    frames = Path('/tmp/gnome-frames')
    frames.mkdir()
    log = Path('/qa/frames.log')
    task = checked_start(stack,
        ['gst-launch-1.0', '-v', 'pipewiresrc', f'path={nodes[0]}', '!', 'videoconvert', '!', 'pngenc', '!',
        'multifilesink', 'max-files=6', 'location=' + str(frames / 'frame-%07d.png')], log)

    def capture(name, since=0):
        check_alive(task, log)

        def image():
            check_alive(task, log)
            for path in sorted(frames.glob('*.png'), reverse=True):
                try:
                    if path.stat().st_mtime_ns >= since:
                        data = path.read_bytes()
                        if data.endswith(b'IEND\xaeB`\x82'):
                            (Path('/qa') / (name + '.png')).write_bytes(data)
                            return True
                except FileNotFoundError:
                    continue
            return None
        try:
            return wait_for(image, 2, 'Private GNOME monitor did not deliver fresh frames')
        except TimeoutError:
            return False
    return capture


def exercise(stack, bus, display, record, app, outcome, capture, notification_only=False):
    trace = Path('/qa/gnome-notification-bus.log')
    checked_start(stack, ['dbus-monitor', '--session', "type='method_call',interface='org.gtk.Notifications'"], trace)
    # Let the first compositor repaint and record the screen before our portal notification.
    record('capture_before', capture('before-notification'))
    task, log = app('notify')
    record('notify', outcome(task, log))
    wait_for(lambda: 'Synthetic notification' in trace.read_text(), 4,
        'GNOME notification backend did not relay the synthetic content')
    since = time.time_ns()
    display.key(0xffeb, True)
    display.key(ord('v'), True)
    display.key(ord('v'), False)
    display.key(0xffeb, False)
    time.sleep(0.5)
    record('capture_notification_list', capture('notification', since))
    since = time.time_ns()
    task, log = app('withdraw')
    record('withdraw', outcome(task, log))
    wait_for(lambda: 'member=RemoveNotification' in trace.read_text(), 4, 'GNOME withdrawal was not observed')
    time.sleep(0.35)
    record('capture_after', capture('withdrawn', since))
    if notification_only:
        return
    task, log = app('background')
    # The real frontend may issue an interactive Access dialog; retain a clean refusal if the backend has no handler.
    status = outcome(task, log)
    entry = Path.home() / '.config/autostart/org.example.IfwPortalDialog.desktop'
    record('background', {'response': status, 'entry': entry.read_text() if entry.exists() else None})
    enabled = any(('autostart=true' in line for line in status))
    if entry.exists() != enabled:
        raise RuntimeError('GNOME autostart response and actual entry disagree')
    if not enabled or 'X-XDP-Autostart=org.example.IfwPortalDialog' not in entry.read_text():
        raise RuntimeError('GNOME did not grant and persist the synthetic Flatpak startup entry')
    task, log = app('background-off')
    disabled = outcome(task, log)
    record('autostart_disabled', {'response': disabled, 'entry_exists': entry.exists()})
    if entry.exists() or not any('autostart=false' in row for row in disabled):
        raise RuntimeError('Disabling autostart did not remove the real entry')
    from gi.repository import Gio, GLib
    store = 'org.freedesktop.impl.portal.PermissionStore'
    bus.call_sync(store, '/org/freedesktop/impl/portal/PermissionStore', store, 'SetPermission',
                  GLib.Variant('(sbssas)', ('background', True, 'background', 'org.example.IfwPortalDialog', ['no'])),
                  None, Gio.DBusCallFlags.NONE, 2000, None)
    task, log = app('background')
    denied = outcome(task, log)
    record('background_denied', {'response': denied, 'entry_exists': entry.exists()})
    if entry.exists() or not any('code=1 background=false autostart=false' in row for row in denied):
        raise RuntimeError('The explicitly denied synthetic app regained background access')
